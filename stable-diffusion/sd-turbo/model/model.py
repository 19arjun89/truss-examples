import base64
from io import BytesIO

from diffusers import AutoPipelineForText2Image
from PIL import Image
import torch

DEFAULT_NUM_STEPS = 1
# SD Turbo does not use guidance_scale; disable it by setting to 0.0.
GUIDANCE_SCALE = 0.0

class Model:
    def __init__(self, **kwargs):
        self._model = None

    def load(self):
        self.model = AutoPipelineForText2Image.from_pretrained(
            "stabilityai/sd-turbo", torch_dtype=torch.float16, variant="fp16"
        )
        self.model.to("cuda")
    
    def convert_to_b64(self, image: Image) -> str:
        buffered = BytesIO()
        image.save(buffered, format="JPEG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return img_b64

    def predict(self, model_input):
        prompt = model_input.get("prompt")
        num_steps = int(model_input.get("num_steps", DEFAULT_NUM_STEPS))
        if num_steps < 1 or num_steps > 4:
            return {"result": "Bad input: num_steps must be between 1 and 4"}
        output_image = self.model(
            prompt=prompt, num_inference_steps=num_steps, guidance_scale=GUIDANCE_SCALE
        ).images[0]
        return {"result": self.convert_to_b64(output_image)}
