
# local development
uvicorn app.main:app --reload --host 127.0.0.1 --port 4222

# ngrok
python ngrokport.py 4222

# environment
conda activate pyx

# chatgpt link about WA voice notes to chat_gpt
https://chatgpt.com/share/68a96826-b2b4-8011-8eac-4013e180e3db

# deployment

# works but deprecated
zip -r ../mxwa.zip . \
  -x "node_modules/*" ".git/*" ".venv/*" "venv/*" "__pycache__/*" "*.pyc" ".DS_Store" "*.log" "*.tar.gz" "*.zip"

az webapp deployment source config-zip --resource-group Development --name MxWaWebHook --src ../mxwa.zip


# new version
# from INSIDE your project folder
zip -r ../mxwa.zip . \
  -x "node_modules/*" ".git/*" ".venv/*" "venv/*" "__pycache__/*" "*.pyc" ".DS_Store" "*.log" "*.tar.gz" "*.zip"

az webapp deploy \
  --resource-group Development \
  --name MxWaWebHook \
  --src-path ../mxwa.zip \
  --type zip \
  --restart true \
  --clean true
