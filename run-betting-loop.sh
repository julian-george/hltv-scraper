while [ true ]
do
    timeout 6h ./run-betting.sh
    sudo rm -rf /tmp/*
done