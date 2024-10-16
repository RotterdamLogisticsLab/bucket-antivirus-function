FROM amazonlinux:2

# Set up working directories
RUN mkdir -p /opt/app
RUN mkdir -p /opt/app/build
RUN mkdir -p /opt/app/bin/

# Copy in the lambda source
WORKDIR /opt/app
COPY ./*.py /opt/app/
COPY requirements.txt /opt/app/requirements.txt

# put your cert in root of project
COPY ZscalerRootCA.crt /etc/ssl/certs/
RUN cat /etc/ssl/certs/ZscalerRootCA.crt >> /etc/ssl/certs/ca-bundle.crt

# Install packages
RUN yum update -y
RUN amazon-linux-extras install epel -y
# RUN yum install -y https://archives.fedoraproject.org/pub/archive/epel/7.9/x86_64/Packages/e/epel-release-7-12.noarch.rpm
RUN yum install -y cpio python3-pip yum-utils zip unzip less compat-openssl10

# This had --no-cache-dir, tracing through multiple tickets led to a problem in wheel
RUN pip3 install -r requirements.txt
RUN rm -rf /root/.cache/pip

# Download libraries we need to run in lambda
WORKDIR /tmp
RUN yumdownloader -x \*i686 --archlist=x86_64 clamav clamav-lib clamav-update json-c pcre2 libprelude gnutls libtasn1 lib64nettle nettle libtool-ltdl libxml2 bzip2-libs xz-libs
RUN rpm2cpio clamav-0*.rpm | cpio -idmv
RUN rpm2cpio clamav-lib*.rpm | cpio -idmv
RUN rpm2cpio clamav-update*.rpm | cpio -idmv
RUN rpm2cpio json-c*.rpm | cpio -idmv
RUN rpm2cpio pcre*.rpm | cpio -idmv
RUN rpm2cpio gnutls* | cpio -idmv
RUN rpm2cpio nettle* | cpio -idmv
RUN rpm2cpio lib* | cpio -idmv
RUN rpm2cpio *.rpm | cpio -idmv
RUN rpm2cpio libtasn1* | cpio -idmv
RUN rpm2cpio libtool-ltdl*.rpm | cpio -vimd
RUN rpm2cpio libxml2*.rpm | cpio -vimd
RUN rpm2cpio bzip2-libs*.rpm | cpio -vimd
RUN rpm2cpio xz-libs*.rpm | cpio -vimd

# Copy over the binaries and libraries
RUN cp /tmp/usr/bin/clamscan /tmp/usr/bin/freshclam /tmp/usr/lib64/* /usr/lib64/libpcre.so.1 /usr/lib64/libssl.so.10 /usr/lib64/libcrypto.so.10 /opt/app/bin/

# Fix the freshclam.conf settings
RUN echo "DatabaseMirror database.clamav.net" > /opt/app/bin/freshclam.conf
RUN echo "CompressLocalDatabase yes" >> /opt/app/bin/freshclam.conf

# Create the zip file
WORKDIR /opt/app
RUN zip -r9 --exclude="*test*" /opt/app/build/lambda.zip *.py bin

WORKDIR /usr/local/lib/python3.7/site-packages
RUN zip -r9 /opt/app/build/lambda.zip *

WORKDIR /opt/app
