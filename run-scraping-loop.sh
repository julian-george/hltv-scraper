while [ true ]
do
   timeout 10m ./run-scraping.sh;
   sleep 600
   sudo rm -rf /tmp/*
done