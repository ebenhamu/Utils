docker swarm init   


# docker swarm join --token <token> <manager-node-ip>:2377


docker node ls  / list nodes 

docker node promote worker1

# make a node to be a manager 
docker node promote <node name >   

docker service ps

docker service ls
