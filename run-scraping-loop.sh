while [ true ]
do
   timeout 30m ./run-scraping.sh;
   sleep 600
   sudo rm -rf /tmp/*
done