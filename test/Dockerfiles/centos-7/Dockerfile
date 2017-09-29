
FROM openshift/base-centos7

RUN yum install -y epel-release \
    && yum install -y  python-devel python-pip \
    && pip install psutil

# Turn off ssh host key checking. Avoid yes/no prompts for user input
RUN echo $'Host * \n\
   StrictHostKeyChecking no \n\
   UserKnownHostsFile=/dev/null' >> /etc/ssh/ssh_config
