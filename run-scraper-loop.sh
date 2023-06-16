while [ true ]
do
   xvfb-run --auto-servernum --server-num=1 yarn start;
   sleep 600
done