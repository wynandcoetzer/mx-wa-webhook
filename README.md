
# local development
uvicorn app.main:app --reload --host 127.0.0.1 --port 4222

# ngrok
python ngrokport.py 4222

# environment
conda activate pyx

# chatgpt link about WA voice notes to chat_gpt
https://chatgpt.com/share/68a96826-b2b4-8011-8eac-4013e180e3db

# deployment
az webapp deploy --src-path ./mx-wa-webhook --type zip --resource-group Development --name MxWaWebHook