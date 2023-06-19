cd prediction
while true 
do
    timeout 6h "xvfb-run --auto-servernum --server-num=1 python3 betting.py"
done