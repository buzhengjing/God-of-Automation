# Step 3 — Tag and Push Image

Purpose:

Tag the docker image with standardized naming and upload to Harbor.

Example tag command:

docker tag flagos:2603031041 \
harbor.baai.ac.cn/flagrelease-public/flagrelease-nvidia-release-model_qwen3.5-35b-a3b-tree_0.4.0-3.5-gems_4.2.1rc0-scale_none-cx_none-python_3.12.3-torch_2.10.0-pcp_cuda13.1-gpu_nvidia003-arc_amd64-driver_570.158.01:2603031041

Login Harbor:

docker login harbor.baai.ac.cn

Push image:

docker push <image>

Execute tool:

tools/push_image.sh

Output:

Published docker image on Harbor.