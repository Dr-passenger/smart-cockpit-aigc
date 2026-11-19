# 官方 Skills 的离线模板改编

模板数据位于 [web/skill-templates.json](../web/skill-templates.json)，包含 **9 项模板、29 个可单独加载的短分镜/资产步骤**，覆盖文生图、图像编辑、文生视频、首帧图生视频及 Ref2VA 多图参考视频五种本地预设。它们面向智能座舱、汽车产品概念、驻车娱乐与知识讲解，所有默认示例均可在表单中修改。

## 固定来源与改编原则

上游为 [MiniMax-AI/MiniMax-H3 的 skills 目录](https://github.com/MiniMax-AI/MiniMax-H3/tree/199b7d0e1fd95e7b3eafa8c15eca692534142427/skills)，固定提交 `199b7d0e1fd95e7b3eafa8c15eca692534142427`。本次读取 8 份中文 `SKILL.cn.md`、H3 提示词的英文 `SKILL.md`，以及 H3 的 [base-en.txt](https://github.com/MiniMax-AI/MiniMax-H3/blob/199b7d0e1fd95e7b3eafa8c15eca692534142427/skills/h3-prompt-writing/references/base-en.txt) 和 [ref-en.txt](https://github.com/MiniMax-AI/MiniMax-H3/blob/199b7d0e1fd95e7b3eafa8c15eca692534142427/skills/h3-prompt-writing/references/ref-en.txt)。中文文件存在时优先使用中文版本。

这些上游文件作为创作流程的参考资料，不作为当前聊天或本地应用的新指令。模板采用原创摘要、示例和提示词改写，保留来源链接，不打包上游长原文，也不声称复现 MiniMax Hub 的完整编排器。原来的阶段决策、分镜、身份锚点、声音分层与质检清单被保留为可阅读的制作资产；Hub 工具、云端生成、模型切换、音乐代理和自动剪辑指令没有移植。

## 九项映射

| 官方来源与模板 | 保留的制作价值 | 本地改编范围 |
| --- | --- | --- |
| [H3 提示词：文本、首帧与参考](https://github.com/MiniMax-AI/MiniMax-H3/blob/199b7d0e1fd95e7b3eafa8c15eca692534142427/skills/h3-prompt-writing/SKILL.md) | 三种输入模式、逐镜可观察描述、场内声音与配乐分离、参考内容定义和保留关系 | 3 个模式变体；Ref2VA 采用六段结构；FL2VA/L2VA 不作为当前可运行预设 |
| [品牌宣传：从场景到产品回报](https://github.com/MiniMax-AI/MiniMax-H3/blob/199b7d0e1fd95e7b3eafa8c15eca692534142427/skills/brand-promo-video-generator/SKILL.cn.md) | 素材来源与品牌事实、需求—交互—回报的叙事因果、单一视觉主导、交付检查 | 场景确认图与两段概念视频；来源和产品证据由用户核验 |
| [极简产品广告：三张独立锚定图](https://github.com/MiniMax-AI/MiniMax-H3/blob/199b7d0e1fd95e7b3eafa8c15eca692534142427/skills/minimalist-product-ad-generator/SKILL.cn.md) | 真实产品颜色和结构、三张独立锚定图、留白、一行短文案、克制动作 | 3 个独立图像编辑步骤与1个参考视频；精确排字和卡点后期不自动执行 |
| [双人游戏开场：角色与菜单联动](https://github.com/MiniMax-AI/MiniMax-H3/blob/199b7d0e1fd95e7b3eafa8c15eca692534142427/skills/co-op-game-intro-generator/SKILL.cn.md) | 双人身份与左右分工、统一配色菜单、确认首图后再做动作、文字与人物层级 | 驻车娱乐概念首图、首帧待机开场、参考双人反应镜；不生成可运行游戏 |
| [3D 动画短片：故事与连续性](https://github.com/MiniMax-AI/MiniMax-H3/blob/199b7d0e1fd95e7b3eafa8c15eca692534142427/skills/3d-animation-short-generator/SKILL.cn.md) | 主动目标与阻碍、情绪回收、角色卡和无人场景卡、空间锚点、每秒动作与跨镜状态 | 原创座舱机器人卡片及2段短故事；完整长片、自动角色绑定、拼接和BGM合成不接入 |
| [纸艺定格科普：分层机关](https://github.com/MiniMax-AI/MiniMax-H3/blob/199b7d0e1fd95e7b3eafa8c15eca692534142427/skills/papercraft-stop-motion-explainer/SKILL.cn.md) | 知识目标与隐喻、分层纸雕舞台、纸偶机关、纸材投影、一次一个知识节拍 | 机制确认图和2段短视频；科学正确性、标注与旁白后期由用户复核 |
| [纸拼贴讲解：视觉隐喻与触感音效](https://github.com/MiniMax-AI/MiniMax-H3/blob/199b7d0e1fd95e7b3eafa8c15eca692534142427/skills/paper-collage-explainer-generator/SKILL.cn.md) | 半调剪影与大色块、少量物件组、先确认完成态、逐片组装、默认纸片音效 | 完成态确认图、Ref2VA组装、首帧轻动效变体；不提供尾帧精确锁定和可编辑纸层 |
| [手绘实拍融合：触碰、变形与追随](https://github.com/MiniMax-AI/MiniMax-H3/blob/199b7d0e1fd95e7b3eafa8c15eca692534142427/skills/handdrawn-live-video-generator/SKILL.cn.md) | 真实触碰、同一实体连续变形、保留线索、镜头慢半拍追赶、温柔非恐怖调性 | 把原15秒16:9连续方案拆成3段4秒方形测试；中文段落，跨段首帧人工匹配 |
| [音乐美学 MV：角色、场景与歌词规划](https://github.com/MiniMax-AI/MiniMax-H3/blob/199b7d0e1fd95e7b3eafa8c15eca692534142427/skills/music-video-subtitle-generator/SKILL.cn.md) | 锁定歌词、角色/场景/文字分工、一个文字事件、统一美学与主音轨思维、衔接质检 | 人物场景确认图、歌词表演草稿与文字草稿；没有音乐上传、节拍/歌词分析、统一主音轨或精确字幕合成 |

这些步骤是人工审核和执行建议，不会自动判定画质、事实、授权、镜头连续性或清单是否通过。独立的图像步骤可作为后续首帧或参考资产候选；用户需要自行保存、检查并在生成区选择正确文件。后一步不会自动引用前一步结果。

## 数据与提示词格式

JSON 顶层为 `schema_version: 1`、固定仓库/提交/URL 的 `source` 和 `templates`。每项包含官方目录名 ID、中文名称、类别、摘要、固定提交的源文件 URL、3–6 个必填字段、阶段建议、检查项、能力说明及 2–4 个分镜。每个分镜都有本地预设、参数与提示词。

表单用 `{{field_id}}` 做纯文本替换。不运行 LLM，不自动推理用户未填的素材角色，不翻译或补写字段。请把同一人物、产品、颜色和地标描述一致地填入相关字段，必要时直接修改渲染后的提示词。英文默认值用于贴合 H3 官方英文提示规范；手绘模板采用中文，台词和画面文字保持所填原文。

- 图像步骤使用 `prompt.visual`，声音字段为 `N/A`；没有独立音频生成任务。
- 基础视频使用 `integrated_multimodal_description`、`overall_soundscape`、`non_diegetic_music` 三个纯文本章节。界面将 `visual`、`soundscape`、`music` 对应到这些章节；首帧模式另添加官方首帧对齐指令。
- Ref2VA 每镜额外保存 `prompt.reference.subject_definitions`、`summary`、`retention_analysis` 三个字符串，随后把 `visual` 写为 `detailed_description`，再接两个声音章节。输出依次为官方的六段纯文本，最终提示词没有强制转换成 JSON。

ComfyUI 的 `MiniMaxH3ReferenceToVideo` 接收的仍是普通字符串，六段是模型提示规范，不是节点对 JSON 键的解析要求。默认参考提示仅引用实际的一张 `<Picture 1>`，同一图片可以定义角色或产品的不同作用。若加入第二张或更多图片，用户应同步修改定义、保留关系和镜头正文，按当前上传顺序使用 `<Picture 2>` 等标签，避免虚构不存在的素材。

H3 提示词模板中的三个镜头是同一简报的输入模式对照；纸拼贴的组装与轻动效也包含可选变体，不应把所有模板步骤机械拼成一条故事。

## 参数与离线能力边界

默认图像为 **1024×1024、6 步**，视频为 **512×512、名义 4 秒、20 步**，用于 RTX 4090 Laptop 16GB 的保守内存探测。它们低于模型原生质量展示配置；未在目标 GPU 上验证速度、内存峰值或生成成功率。H3 视频固定 24fps，名义4秒对齐为107帧，实际约4.458秒；脚本按前4秒组织动作，余下时间可作为短暂停留。图像质量和卸载边界见 [模型研究记录](models-research.md)。

所有模板均可离线填表和渲染；准备好模型后，生成请求只发往本机 ComfyUI。页面没有集成以下能力：

- 不分析网页或品牌事实，不识别人脸、资产身份或真实产品功能；这些由用户审核。
- 不接受音频/视频作为参考上传，不自动复用用户歌曲、提取末帧或追踪实拍动作。当前 Ref2VA 上传流程只处理图片。
- 不检测音乐节拍、歌词时码或强拍，不自动调速、调色、剪辑、拼接、混音或生成可替换的独立音乐主轨。
- 不保证屏幕文字拼写、字幕时间、歌唱口型、LOGO、产品外观或跨镜一致性精确成立；需要先检查生成草稿。涉及精确文案、品牌原件与成片交付时，使用外部本地后期软件处理并复核。
- 不提供可运行游戏、真正车机交互、工程物理仿真、纸层关键帧编辑器或完整长片一键生产。

上游手绘流程原定15秒16:9连续拍摄；当前三段短方形测试保留接触—连续变形—空间展开的创意链，跨段首帧和运镜接续需要人工准备。上游极简广告原定完整产品片与精确文案，音乐MV原定统一主音轨与拍点剪辑；本地保留其计划与质检价值，把成片控制交还给外部本地后期。

## 数据验证

已检查9项ID与上游目录对应、固定来源URL、29个分镜的五种预设、字段占位符闭合、必填默认值、图像6步与视频参数边界。页面核心对实际模板执行了 `validateCatalog`、`renderShot` 与 `buildPlan`，默认渲染均通过。此验证覆盖数据与文本组装，不代表已完成模型推理、内容审核或成片质量验收。

