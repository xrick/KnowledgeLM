# app/Providers/image_gen_provider/usage.py
from app.Providers.image_gen_provider import get_image_gen_manager

# 方式 1: 透過 Manager（推薦）
manager = get_image_gen_manager()
image = manager.generate("An astronaut riding a green horse")
manager.release()  # 用完釋放 VRAM

# 方式 2: FastAPI DI
# from fastapi import Depends

# @router.post("/generate")
# async def generate_image(
#     manager: ImageGenManager = Depends(get_image_gen_manager)
# ):
#     image = manager.generate(prompt="A cat in space", num_inference_steps=30)
#     ...

# 方式 3: 多次呼叫 — 模型只載入一次
# m1 = get_image_gen_manager()
# m2 = get_image_gen_manager()
# assert m1 is m2  # True — 同一 Singleton