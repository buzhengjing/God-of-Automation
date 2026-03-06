# Step 2 — Upload to HuggingFace

Login:

hf auth login

Upload model:

hf upload FlagRelease/<model-name> /data/<model-dir> --repo-type model

Execute tool:

tools/upload_hf.sh