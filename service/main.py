from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel
import json
from urllib import request
import asyncio
from fastapi.middleware.cors import CORSMiddleware
import os
from fastapi import FastAPI, Request
import logging

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 출처 허용
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메소드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)

COMFYUI_URL = "127.0.0.1:8188"  # ComfyUI 서버 IP 및 포트

# 요청 데이터 모델 정의
class WorkflowRequest(BaseModel):
    workflow: dict

# 응답 데이터 모델 정의
class WorkflowResponse(BaseModel):
    image: str  # base64 인코딩된 이미지 데이터

def queue_prompt(prompt_workflow, ip):
    p = {"prompt": prompt_workflow}
    data = json.dumps(p).encode('utf-8')
    req = request.Request(f"http://{ip}/prompt", data=data)
    try:
        res = request.urlopen(req)
        if res.code != 200:
            raise Exception(f"Error: {res.code} {res.reason}")
        return json.loads(res.read().decode('utf-8'))['prompt_id']
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def check_progress(prompt_id: str, ip: str):
    while True:
        try:
            req = request.Request(f"http://{ip}/history/{prompt_id}")
            res = request.urlopen(req)
            if res.code == 200:
                history = json.loads(res.read().decode('utf-8'))
                if prompt_id in history:
                    return history[prompt_id]
        except Exception as e:
            print(f"Error checking progress: {str(e)}")
        await asyncio.sleep(1)  # 1초 대기

@app.get("/")
def read_root():
    return {"message": "Hello, FastAPI!"}

@app.get("/workflow/test")
async def test():
    try:
        with (open("./workflow/test_api.json", "r", encoding="utf-8")) as f:
            workflow_request = WorkflowRequest(workflow=json.loads(f.read()))

        prompt_id = queue_prompt(workflow_request.workflow, COMFYUI_URL)
        result = await check_progress(prompt_id, COMFYUI_URL)      
    
        # 결과에서 마지막 이미지 URL 추출
        final_image_url = None
        for node_id, node_output in result['outputs'].items():
            if 'images' in node_output:
                for image in node_output['images']:
                    final_image_url = f"http://{COMFYUI_URL}/view?filename={image['filename']}&type=temp"
        
        if final_image_url:
            return {"status": "completed", "image": final_image_url}
        else:
            return {"status": "completed", "image": None}
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/workflow/cloth")
async def cloth(img_model: UploadFile = File(...), img_product: UploadFile = File(...)):
    try:
        # 이미지를 저장할 경로 설정
        for img in [img_model, img_product]:
            image_path = f"./ComfyUI/input/{img.filename}"
            with open(image_path, "wb") as f:
                f.write(await img.read())

        # 저장된 이미지 경로를 워크플로우에 포함
        with (open("./workflow/cloth_api.json", "r", encoding="utf-8")) as f:
            workflow_request = WorkflowRequest(workflow=json.loads(f.read()))

        # 이미지 경로를 워크플로우에 추가
        workflow_request.workflow["3"]["inputs"]["image"] = img_model.filename
        workflow_request.workflow["4"]["inputs"]["image"] = img_product.filename

        # ComfyUI에 워크플로우 전송
        prompt_id = queue_prompt(workflow_request.workflow, COMFYUI_URL)
        result = await check_progress(prompt_id, COMFYUI_URL)

        # 결과에서 마지막 이미지 URL 추출
        final_image_url = None
        for node_id, node_output in result['outputs'].items():
            if 'images' in node_output:
                for image in node_output['images']:
                    final_image_url = f"http://{COMFYUI_URL}/view?filename={image['filename']}&type=temp"

        # 반환할 이미지 URL
        if final_image_url:
            return {"status": "completed", "images": final_image_url}
        else:
            return {"status": "completed", "images": None}
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Uvicorn 실행
import uvicorn

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)