'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const core = require('../web/template-core.js');

const REVISION = '199b7d0e1fd95e7b3eafa8c15eca692534142427';
const REPO = 'https://github.com/MiniMax-AI/MiniMax-H3';
const PRESETS = ['text-image', 'image-image', 'text-video', 'image-video', 'reference-video'];
const catalogPath = path.join(__dirname, '../web/skill-templates.json');
const copy = value => JSON.parse(JSON.stringify(value));

function fixture() {
  return {
    schema_version: 1,
    source: { repository: REPO, revision: REVISION, url: `${REPO}/tree/${REVISION}/skills` },
    templates: Array.from({ length: 9 }, (_, index) => ({
      id: index === 0 ? '3d-animation-short-generator' : `template-${index + 1}`, name: `模板 ${index + 1}`, category: '测试', summary: '受控工作流',
      source_url: `${REPO}/blob/${REVISION}/skills/example/SKILL.cn.md`,
      fields: [
        { id: 'subject', label: '主角', type: 'text', default: '智能座舱', required: true },
        { id: 'style', label: '风格', type: 'textarea', default: '自然光', required: true },
      ],
      stages: ['准备 {{subject}}', '生成'], checklist: ['确认 {{style}}'], notes: ['本地处理'],
      shots: PRESETS.map((preset, shotIndex) => ({
        id: `shot-${shotIndex + 1}`, title: `镜头 ${shotIndex + 1}`, preset,
        description: '{{subject}} 的镜头',
        settings: { width: preset.endsWith('image') ? 1024 : 512, height: preset.endsWith('image') ? 1024 : 512, steps: preset.endsWith('image') ? 6 : 20, duration: 4 },
        prompt: {
          visual: '{{subject}}；{{style}}；<Picture 1> 与 [Shot 1]。',
          soundscape: '{{subject}} 的环境声', music: '低声音乐，{{style}}',
          ...(preset === 'reference-video' ? { reference: {
            subject_definitions: '<Picture 1>: {{subject}}',
            summary: '{{subject}} 与环境互动', retention_analysis: '保留 <Picture 1> 的外观',
          } } : {}),
        },
      })),
    })),
  };
}

function assertBackendSettings(rendered) {
  const { width, height, steps, duration } = rendered.settings;
  const image = ['text-image', 'image-image'].includes(rendered.preset);
  assert.ok(Number.isInteger(width) && width >= 256 && width <= 4096 && width % 32 === 0);
  assert.ok(Number.isInteger(height) && height >= 256 && height <= 4096 && height % 32 === 0);
  assert.ok(Number.isInteger(steps) && steps >= 1 && steps <= 100);
  assert.ok(Number.isInteger(duration) && duration >= (image ? 1 : 4) && duration <= 15);
  if (image) assert.equal(steps, 6);
  else assert.ok(width * height <= 1280 * 768);
  assert.ok(rendered.prompt.trim().length > 0 && rendered.prompt.length <= 16000);
}

test('UMD exposes the same API in a browser without requiring Node', () => {
  const context = { URL };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/template-core.js'), 'utf8'), context);
  assert.deepEqual(Object.keys(context.H3TemplateCore).sort(), ['buildPlan', 'renderShot', 'validateCatalog']);
});

test('renders default shots for nine valid templates without changing source objects', () => {
  const catalog = fixture();
  const original = copy(catalog);
  assert.equal(core.validateCatalog(catalog), catalog);
  for (const template of catalog.templates) {
    for (const shot of template.shots) {
      const rendered = core.renderShot(template, shot, {});
      assertBackendSettings(rendered);
      assert.ok(rendered.prompt.includes('智能座舱'));
      assert.ok(!rendered.prompt.includes('{{subject}}'));
    }
  }
  assert.deepEqual(catalog, original);
});

test('actual nine-template catalog renders every default shot with backend-compatible settings', { skip: !fs.existsSync(catalogPath) && 'Research catalog is not generated yet' }, () => {
  const catalog = core.validateCatalog(JSON.parse(fs.readFileSync(catalogPath, 'utf8')));
  assert.equal(catalog.templates.length, 9);
  for (const template of catalog.templates) {
    const plan = core.buildPlan(catalog, template, {});
    assert.equal(plan.shots.length, template.shots.length);
    for (const shot of template.shots) assertBackendSettings(core.renderShot(template, shot, {}));
  }
});

test('newlines, quotes and angle brackets remain exact data in image and video prompts', () => {
  const template = fixture().templates[0];
  const value = '第一行\n"quoted" <script>alert(1)</script> & <Picture 2>';
  for (const shot of template.shots) {
    const result = core.renderShot(template, shot, { subject: value });
    assert.ok(result.prompt.includes(value));
    assert.ok(!result.prompt.includes('&lt;script&gt;'));
    assert.ok(!result.prompt.includes('\\n\\"quoted'));
  }
});

test('placeholder substitution is strictly one pass and user values are not template code', () => {
  const template = fixture().templates[0];
  const rendered = core.renderShot(template, template.shots[0], { subject: '{{style}} {{unknown}}', style: '固定风格' });
  assert.equal(rendered.prompt, '{{style}} {{unknown}}；固定风格；<Picture 1> 与 [Shot 1]。');
});

test('rejects unknown placeholders, unknown field keys and empty required values', () => {
  const template = fixture().templates[0];
  const wrong = copy(template.shots[0]);
  wrong.prompt.visual = '{{missing}}';
  assert.throws(() => core.renderShot(template, wrong, {}), /未知模板字段/);
  wrong.prompt.visual = '{{missing {{subject}} }}';
  assert.throws(() => core.renderShot(template, wrong, {}), /占位符格式/);
  assert.throws(() => core.renderShot(template, template.shots[0], { missing: 'x' }), /未知模板字段/);
  assert.throws(() => core.renderShot(template, template.shots[0], { subject: ' \n\t ' }), /为空/);
  assert.throws(() => core.renderShot(template, template.shots[0], { subject: 123 }), /为空/);
});

test('video uses official three text sections and I2V starts with first-frame alignment', () => {
  const template = fixture().templates[0];
  const t2v = core.renderShot(template, template.shots[2], {}).prompt;
  assert.equal(t2v, 'integrated_multimodal_description: 智能座舱；自然光；<Picture 1> 与 [Shot 1]。\n\noverall_soundscape: 智能座舱 的环境声\n\nnon_diegetic_music: 低声音乐，自然光');
  assert.throws(() => JSON.parse(t2v));
  const i2v = core.renderShot(template, template.shots[3], {}).prompt;
  assert.equal(i2v, 'For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n' + t2v);
});

test('Ref2VA preserves Picture labels and renders six official sections in order', () => {
  const template = fixture().templates[0];
  const ref = core.renderShot(template, template.shots[4], {}).prompt;
  const headings = [...ref.matchAll(/^(subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|non_diegetic_music):/gm)].map(match => match[1]);
  assert.deepEqual(headings, ['subject_definitions', 'summary', 'retention_analysis', 'detailed_description', 'overall_soundscape', 'non_diegetic_music']);
  assert.ok(ref.includes('<Picture 1>'));
  assert.ok(ref.includes('[Shot 1]'));
  assert.ok(!ref.includes('integrated_multimodal_description:'));
  const missing = copy(template);
  delete missing.shots[4].prompt.reference;
  assert.throws(() => core.renderShot(missing, missing.shots[4], {}), /Ref2VA/);
});

test('rejects fields over 2000 and rendered prompts over 16000 characters', () => {
  const template = fixture().templates[0];
  assert.throws(() => core.renderShot(template, template.shots[0], { subject: 'x'.repeat(2001) }), /长度超限/);
  const large = copy(template);
  large.shots[0].prompt.visual = '{{subject}}'.repeat(9);
  assert.throws(() => core.renderShot(large, large.shots[0], { subject: 'x'.repeat(2000) }), /完整提示词/);
});

test('rejects unfixed, forged, cross-repository and mixed-revision sources', () => {
  for (const url of [
    `${REPO}/tree/main/skills`,
    `https://github.com.evil.example/MiniMax-AI/MiniMax-H3/tree/${REVISION}/skills`,
    `${REPO}/tree/${REVISION}/skills?redirect=https://evil.example`,
    `https://github.com/other/MiniMax-H3/tree/${REVISION}/skills`,
    `javascript:alert(1)`,
  ]) {
    const catalog = fixture();
    catalog.source.url = url;
    assert.throws(() => core.validateCatalog(catalog), /来源/);
  }
  const changed = fixture();
  changed.templates[0].source_url = `${REPO}/blob/${'a'.repeat(40)}/skills/a.md`;
  assert.throws(() => core.validateCatalog(changed), /来源/);
});

test('rejects settings that violate the GenerationRequest constraints', () => {
  for (const mutation of [
    shot => { shot.settings.width = 511; },
    shot => { shot.settings.height = 8192; },
    shot => { shot.settings.steps = 0; },
    shot => { shot.settings.duration = 3; },
    shot => { shot.settings.width = 1280; shot.settings.height = 1024; },
  ]) {
    const template = fixture().templates[0];
    mutation(template.shots[2]);
    assert.throws(() => core.renderShot(template, template.shots[2], {}));
  }
  const image = fixture().templates[0];
  image.shots[0].settings.steps = 20;
  assert.throws(() => core.renderShot(image, image.shots[0], {}), /固定 6 步/);
});

test('plan contains provenance, resolved fields and every rendered shot as JSON data', () => {
  const catalog = fixture();
  const plan = core.buildPlan(catalog, catalog.templates[0], { subject: '测试车辆' });
  assert.deepEqual(plan.source, catalog.source);
  assert.equal(plan.template.id, catalog.templates[0].id);
  assert.equal(plan.fields.subject, '测试车辆');
  assert.equal(plan.fields.style, '自然光');
  assert.equal(plan.shots.length, 5);
  assert.equal(plan.stages[0], '准备 测试车辆');
  assert.equal(plan.checklist[0], '确认 自然光');
  assert.deepEqual(JSON.parse(JSON.stringify(plan)), plan);
  assert.deepEqual(core.buildPlan(catalog, catalog.templates[0].id, { subject: '测试车辆' }), plan);
  assert.throws(() => core.buildPlan(catalog, 'not-in-catalog', {}), /模板不在目录/);
});
