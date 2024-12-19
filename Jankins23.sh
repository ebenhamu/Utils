# create 5 instances
# swarm1 , swarm2 , swarm3 , storage , agent (jankins)


sudo hosnamectl set-hostname <node name>
sudo apt -y update
sudo apt -y install docker.io

cat<<EOF>>/etc/hosts
<ip> swarm1
<ip> swarm2
<ip> swarm3  
<ip> swarm4
<ip> storage
<ip> agent
EOF



