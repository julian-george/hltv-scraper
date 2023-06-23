while [ true ]
do
    timeout 6h ./run-betting.sh
    echo "Restarting"
    sudo rm -rf /tmp/*
done