from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Literal["image", "video"]
    mode: Literal["t2i", "edit", "t2v", "i2v", "ref2va"] | None = None
    backend: Literal["local"] = "local"
    prompt: str = Field(min_length=1, max_length=16000)
    width: int = Field(default=1024, ge=256, le=4096)
    height: int = Field(default=1024, ge=256, le=4096)
    seed: int = Field(default=-1, ge=-1, le=2**53 - 1)
    steps: int = Field(default=6, ge=1, le=100)
    duration: int = Field(default=4, ge=1, le=15)
    reference_asset_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    reference_asset_ids: list[Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]] = Field(default_factory=list, max_length=9)
    workflow: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def model_defaults(cls, data):
        if isinstance(data, dict) and data.get("model") == "video":
            data = {"width": 512, "height": 512, "steps": 20, **data}
        return data

    @model_validator(mode="after")
    def validate_model_settings(self):
        self.prompt = self.prompt.strip()
        if not self.prompt:
            raise ValueError("提示词不能为空")
        refs = list(dict.fromkeys(([self.reference_asset_id] if self.reference_asset_id else []) + self.reference_asset_ids))
        if len(refs) > 9:
            raise ValueError("Ref2VA 最多支持 9 张参考图片")
        if self.mode is None:
            self.mode = ("edit" if refs else "t2i") if self.model == "image" else (
                "ref2va" if self.reference_asset_ids else "i2v" if refs else "t2v")
        allowed = {"image": {"t2i", "edit"}, "video": {"t2v", "i2v", "ref2va"}}
        if self.mode not in allowed[self.model]:
            raise ValueError("工作流类型与所选模型不匹配")
        if self.mode in {"edit", "i2v", "ref2va"} and not refs:
            raise ValueError("此工作流需要上传参考图片")
        if self.mode in {"t2i", "t2v"} and refs:
            raise ValueError("纯文本工作流不能包含参考图片")
        if self.mode in {"edit", "i2v"} and len(refs) != 1:
            raise ValueError("此工作流需要恰好一张参考图片；多图视频请使用 Ref2VA")
        if self.mode == "ref2va":
            self.reference_asset_ids = refs
            self.reference_asset_id = None
        elif refs:
            self.reference_asset_id = refs[0]
            self.reference_asset_ids = []
        if self.width % 32 or self.height % 32:
            raise ValueError("宽和高必须是 32 的倍数")
        if self.model == "image" and self.steps != 6:
            raise ValueError("H3-Image 使用固定的 6 步蒸馏采样，请将步数设为 6")
        if self.model == "video":
            if self.width * self.height > 1280 * 768:
                raise ValueError("笔记本视频预设最高约 1MP；请从 512×512、4秒开始")
            if self.duration < 4:
                raise ValueError("H3 视频时长最少 4 秒")
        if self.workflow is not None:
            import json
            if len(json.dumps(self.workflow, ensure_ascii=False)) > 250000:
                raise ValueError("工作流过大")
        return self
