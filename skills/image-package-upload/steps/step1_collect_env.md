# Step 1 — Collect Environment Information

Purpose:

Collect software and hardware versions required for image naming.

Commands:

tree version
pip show flagtree

gems version
pip show flaggems

scale version
pip show flagscale

cx version
pip show flagcx

python version
python -V

torch version
python -c "import torch;print(torch.__version__)"

cuda version
nvcc -V

driver version
nvidia-smi

Execute tool:

tools/collect_env.sh

Output:

Environment version table used for docker image naming.