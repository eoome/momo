# ModernWMS - Warehouse Management System

A simple, complete and open source warehouse management system

# Contents

- [ModernWMS - Warehouse Management System](#modernwms---warehouse-management-system)
- [Contents](#contents)
  - [Introduction](#introduction)
  - [Requirements](#requirements)
    - [Linux OS](#linux-os)
    - [Windows OS](#windows-os)
  - [Installation](#installation)
    - [Linux shell](#linux-shell)
    - [Windows PowerShell](#windows-powershell)
  - [Frequently Asked Questions (FAQ)](#frequently-asked-questions-faq)
  - [Usage](#usage)
  - [License](#license)

## Introduction 

  The inventory management system is a set of small logistics warehousing supply chain processes that we have summarized from years of ERP system research and development. In the process of work, many of our small and medium-sized enterprises, due to limited IT budget, cannot use the right system for them, but there are real needs in warehouse management, that's how we started the project. To help some people who need it.

## Requirements

### Linux OS

+ Ubuntu 18.04(LTS),20.04(LTS),22.04(LTS)
+ CentOS Stream 8,9
+ RHEL 8(8.7),9(9.1)
+ Debian 10,11
+ openSUSE 15

### Windows OS

+ Windows 10(1607+),11(21H2+)
+ Windows Server 2012+

## Installation

### Linux shell

+ download the source code and compile
  + Step 1, download the source code

  ```bash
  cd /tmp/ &amp;&amp; wget https://gitee.com/modernwms/ModernWMS/repository/archive/master.zip
  ```  

  + Step 2, Install .NET SDK and NodeJS

  ```bash
  wget https://packages.microsoft.com/config/ubuntu/20.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
  sudo dpkg -i packages-microsoft-prod.deb
  sudo apt-get update &amp;&amp; sudo apt-get install -y dotnet-sdk-7.0
  curl -fsSL https://deb.nodesource.com/setup_16.x | sudo -E bash -
  sudo apt install -y nodejs
  sudo apt-get install gcc g++ make
  sudo npm install -g yarn
  ```  

  + Step 3, compile frontend and backend

  ```bash
  sudo apt install unzip
  cd /tmp/ &amp;&amp; unzip master.zip &amp;&amp; cd ./ModernWMS-master
  sudo mkdir -p /ModernWMS/frontend/ /ModernWMS/backend/
  cd /tmp/ModernWMS-master/frontend/ 
  sudo sed -i 's#http://127.0.0.1#http://IP address#g' ./.env.production
  sudo yarn &amp;&amp; sudo yarn build &amp;&amp; sudo cp -rf /tmp/ModernWMS-master/frontend/dist/* /ModernWMS/frontend/
  cd /tmp/ModernWMS-master/backend/ &amp;&amp; sudo dotnet publish &amp;&amp; sudo cp -rf /tmp/ModernWMS-master/backend/ModernWMS/bin/Debug/net7.0/publish/* /ModernWMS/backend/

  ```  
  + Step 4, database initialization 
  1) Modify `/ModernWMS/backend/appsettings.json`，When configuring the connection pool, ensure to update the database IP address, port, username, and password to establish a successful connection.
   2) Download the database script and initialize the database (MySql, SQLServer, Postgresql available)

  
  + Step 5, Install Nginx

  ```bash
  cd /tmp/ &amp;&amp; wget http://nginx.org/download/nginx-1.18.0.tar.gz 
  tar -zxvf nginx-1.18.0.tar.gz &amp;&amp; cd nginx-1.18.0
  sudo ./configure --prefix=/etc/nginx --with-http_secure_link_module --with-http_stub_status_module --with-http_realip_module --without-http_rewrite_module --without-http_gzip_module
  sudo make &amp;&amp; sudo make install
  sudo cp -rf /ModernWMS/frontend/* /etc/nginx/html/
  nohup sudo /etc/nginx/sbin/nginx -g 'daemon off;' &amp;
  cd /ModernWMS/backend/ &amp;&amp; nohup sudo dotnet ModernWMS.dll --urls http://0.0.0.0:20011 &amp;
  ```  
  
### Windows PowerShell

+ download the source code and compile
  + Step 1, download the source code
  ```PowerShell
  cd C:\
  wget -Uri https://gitee.com/modernwms/ModernWMS/repository/archive/master.zip  -OutFile master.zip
  Expand-Archive -Path C:\master.zip -DestinationPath C:\
  ```
  + Step 2, Install .NET SDK and NodeJS
  ```PowerShell
  wget -Uri https://download.visualstudio.microsoft.com/download/pr/35660869-0942-4c5d-8692-6e0d4040137a/4921a36b578d8358dac4c27598519832/dotnet-sdk-7.0.101-win-x64.exe  -OutFile dotnet-sdk-7.0.101-win-x64.exe
  .\dotnet-sdk-7.0.101-win-x64.exe /install /quiet /norestart
  wget -Uri https://nodejs.org/dist/v16.13.1/node-v16.13.1-x64.msi  -OutFile node-v16.13.1-x64.msi
  msiexec /i .\node-v16.13.1-x64.msi /passive /norestart
  npm install -g yarn
  ```
  + Step 3, compile frontend and backend
  ```PowerShell
  md C:\ModernWMS\frontend\
  md C:\ModernWMS\backend\
  cd C:\ModernWMS-master\backend
  dotnet publish 
  copy-item -path "C:\ModernWMS-master\backend\ModernWMS\bin\Debug\net7.0\publish\*" -destination "C:\ModernWMS\backend\" -recurse
  copy-Item "C:\ModernWMS-master\backend\ModernWMS\wms.db" -Destination "C:\ModernWMS\backend\"
  cd C:\ModernWMS-master\frontend  
  yarn
  yarn build 
  copy-item -path "C:\ModernWMS-master\frontend\dist\*" -destination "C:\ModernWMS\frontend\" -recurse
  ```
  + Step 4, database initialization 
  1) Modify `C:\ModernWMS\frontend\appsettings.json`，When configuring the connection pool, ensure to update the database IP address, port, username, and password to establish a successful connection.
   2) Download the database script and initialize the database (MySql, SQLServer, Postgresql available)

  
  + Step 5, Install Nginx
  ```PowerShell
  cd C:\
  wget -Uri http://nginx.org/download/nginx-1.16.1.zip -OutFile nginx-1.16.1.zip
  Expand-Archive -Path C:\nginx-1.16.1.zip -DestinationPath C:\
  copy-item -path "C:\ModernWMS\frontend\*" -destination "C:\nginx-1.16.1\html\" -recurse
  cd C:\nginx-1.16.1\
  start nginx.exe
  cd C:\ModernWMS\backend\
  Start-Process -WindowStyle hidden -FilePath "dotnet" "ModernWMS.dll --urls http://0.0.0.0:20011" 
  ```

## Frequently Asked Questions (FAQ)
  1) Open ports 80 and 20011 on the deployment server.For cloud servers, ensure both security group rules and firewall settings allow access to these ports
  2) Errors during installation of dotnet-sdk-7.0 on unsupported OS versions，If encountering dependency issues, modify the download path of dpkg packages
  3) Errors in sudo yarn &amp;&amp; sudo yarn build. Switch to Taobao Registry to resolve dependency installation failures.

## Usage

  ```shell
  Accessing ip address (http://127.0.0.1 or http://the IP address you depolyed) via web browser 
  
  Account: admin 
  Password: 1
  ```

## License

Distributed under the [Apache2.0](https://opensource.org/license/apache-2-0/) License.
