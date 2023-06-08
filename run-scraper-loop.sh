while [ true ]
do
   xvfb-run --auto-servernum --server-num=1 yarn log;
   sleep 600
done