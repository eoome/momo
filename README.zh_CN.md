# ModernWMS - 仓库管理系统

开源的简易完整的仓库管理系统

# 目录

- [ModernWMS - 仓库管理系统](#modernwms---仓库管理系统)
- [目录](#目录)
  - [介绍](#介绍)
  - [必要条件](#必要条件)
    - [Linux OS](#linux-os)
    - [Windows OS](#windows-os)
  - [安装](#安装)
    - [Linux shell](#linux-shell)
    - [Windows PowerShell](#windows-powershell)
  - [常见问题](#常见问题)
  - [使用方法](#使用方法)
  - [版权信息](#版权信息)

## 介绍
  该库存管理系统是，我们从多年ERP系统研发中总结出来的一套针对小型物流仓储供应链流程。 在工作过程中我们很多的中小企业，由于IT预算有限，所以无法用上适合他们的系统，却又实实在在存在仓储管理方面的需求，以此我们开始了这个项目。 为了帮助一些有需要的用户。

## 必要条件

### Linux OS

+ Ubuntu 18.04(LTS),20.04(LTS),22.04(LTS)
+ CentOS Stream 8,9
+ RHEL 8(8.7),9(9.1)
+ Debian 10,11
+ openSUSE 15

### Windows OS

+ Windows 10 版本 1607 或更高版本
+ Windows Server 2012 或更高版本

## 安装

### Linux shell

+ 下载源码后编译
  + 第一步，下载源码

  ```bash
  cd /tmp/ &amp;&amp; wget https://gitee.com/modernwms/ModernWMS/repository/archive/master.zip
  ```

  + 第二步，安装.NET SDK 和 NodeJS

  ```bash
  wget https://packages.microsoft.com/config/ubuntu/20.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
  sudo dpkg -i packages-microsoft-prod.deb
  sudo apt-get update &amp;&amp; sudo apt-get install -y dotnet-sdk-7.0
  curl -fsSL https://deb.nodesource.com/setup_16.x | sudo -E bash -
  sudo apt install -y nodejs
  sudo apt-get install gcc g++ make
  sudo npm install -g yarn
  ```

  + 第三步，编译前端和后端

  ```bash
  sudo apt install unzip
  cd /tmp/ &amp;&amp; unzip master.zip &amp;&amp; cd ./ModernWMS-master
  sudo mkdir -p /ModernWMS/frontend/ /ModernWMS/backend/
  cd /tmp/ModernWMS-master/frontend/ 
  sed -i 's#http://127.0.0.1#http://当前部署服务器的IP地址#g' ./.env.production
  sudo yarn &amp;&amp; sudo yarn build &amp;&amp; sudo cp -rf /tmp/ModernWMS-master/frontend/dist/* /ModernWMS/frontend/
  cd /tmp/ModernWMS-master/backend/ &amp;&amp; sudo dotnet publish &amp;&amp; sudo cp -rf /tmp/ModernWMS-master/backend/ModernWMS/bin/Debug/net7.0/publish/* /ModernWMS/backend/
  ```

  + 第四步，初始化数据库
  
   1) 修改后端目录`/ModernWMS/backend/appsettings.json`文件，连接池配置时注意修改数据库IP地址、端口、账号、密码，确保可以正确连接数据库
   2) 下载数据库脚本，初始化数据库，提供 MySql，SQLServer，Postgresql

  + 第五步，安装nginx

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

+ 下载源码后编译部署
  + 第一步，下载源码
  ```PowerShell
  cd C:\
  wget -Uri https://gitee.com/modernwms/ModernWMS/repository/archive/master.zip  -OutFile master.zip
  Expand-Archive -Path C:\master.zip -DestinationPath C:\
  ```
  + 第二步，安装.NET SDK 和 NodeJS
  ```PowerShell
  wget -Uri https://download.visualstudio.microsoft.com/download/pr/35660869-0942-4c5d-8692-6e0d4040137a/4921a36b578d8358dac4c27598519832/dotnet-sdk-7.0.101-win-x64.exe  -OutFile dotnet-sdk-7.0.101-win-x64.exe
  .\dotnet-sdk-7.0.101-win-x64.exe /install /quiet /norestart
  wget -Uri https://nodejs.org/dist/v16.13.1/node-v16.13.1-x64.msi  -OutFile node-v16.13.1-x64.msi
  msiexec /i .\node-v16.13.1-x64.msi /passive /norestart
  npm install -g yarn
  ```
  + 第三步，编译前端和后端
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
  + 第四步，初始化数据库
  
   1) 修改后端目录`C:\ModernWMS\frontend\appsettings.json`文件，连接池配置时注意修改数据库IP地址、端口、账号、密码，确保可以正确连接数据库
   2) 下载数据库脚本，初始化数据库，提供 MySql，SQLServer，Postgresql

  + 第五步，安装nginx
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

## 业务流程

### 1. 系统初始化和基础数据配置流程

#### 用户权限管理流程

**用户管理系统**：

- 用户注册、登录、密码管理
- 角色创建和权限分配
- 多租户用户隔离机制
- 菜单权限动态配置

#### 基础数据配置流程

**仓库结构配置**：

- 仓库基本信息设置
- 仓库区域层级配置
- 货位管理和定位设置
- 货位属性配置（长宽高、容量、载重等）

**商品信息管理**：

- 商品分类设置
- SPU/SKU商品信息管理
- 供应商和客户信息维护
- 货主信息配置

### 2. 入库业务流程 

#### ASN完整工作流程

**预到货通知管理**：

- **创建ASN单据** - 供应商或采购部门创建预到货通知
- **到货确认** - 仓库接收货物并确认到货状态
- **卸货作业** - 进行货物卸载和初步检查
- **分拣作业** - 按照商品类型和规格进行分拣
- **上架作业** - 将商品放置到指定货位

#### ASN状态管理

系统提供完整的ASN状态跟踪和错误处理机制：

- 状态验证和转换控制
- 数量验证和差异处理
- 操作确认和撤销功能

### 3. 仓内作业管理流程

#### 库存移动作业流程

**仓库移动操作** ：

- 选择源商品和货位信息
- 选择目标货位
- 数量验证（不能超过可用库存）
- 生成二维码支持移动端操作
- 确认移动并更新库存记录

#### 库存加工作业流程

**仓库加工操作**：

- **拆分作业**- 将一个商品拆分为多个商品
- **组合作业** - 将多个商品组合为一个商品
- **加工确认** 
- **调整确认** 

#### 库存调整作业流程

**仓库调整操作** ：

- 选择调整类型（盘点、加工、移库等）
- 商品和货位选择
- 数量输入和原因记录
- 提交调整申请和审核确认

#### 库存冻结作业流程

**仓库冻结操作**：

- 冻结操作 - 将库存标记为不可用状态
- 解冻操作 - 恢复库存的可用状态
- 冻结原因管理和记录

#### 库存盘点作业流程

**仓库盘点操作**：

- 创建盘点计划和任务分配
- 从现有库存或商品目录选择盘点
- 执行实地盘点和数据记录
- 系统自动计算差异数量
- 处理盘点差异和结果确认

### 4. 出库业务流程 (发货管理)

#### 发货管理完整流程

**订单确认阶段**  ：

- 接收出库订单和商品确认
- 库存可用性检查
- 拣货数量分配和批次管理
- 有效期和价格信息确认

**包装处理阶段**：

- 待包装商品管理
- 包装规格配置
- 包装确认操作

#### 发货状态流转管理

**状态转换控制**：

- 预发货 (Status 0) → 新发货 (Status 1)
- 新发货 → 待拣货 (Status 2)
- 待拣货 → 已拣货 (Status 3)
- 已拣货 → 已包装 (Status 4)
- 已包装 → 已称重 (Status 5)
- 已称重 → 出库 (Status 6)
- 出库 → 已签收 (Status 7)

### 5. 库存管理和监控流程

#### 实时库存监控

- 库存数量实时查询
- 批次库存追踪
- 库存预警设置
- 安全库存监控

### 库存分析和报表

- 库存周转分析
- 库存账龄统计
- 库存异常监控
- 库存成本分析

### 6. 系统集成和数据流转

#### API接口调用流程

- 前端发起API请求
- 后端控制器处理和验证
- 业务服务层执行逻辑
- 数据库操作和事务管理
- 返回处理结果和状态更新

#### 权限控制和安全流程

- JWT身份验证机制
- 角色权限检查
- 菜单权限分配
- 操作权限控制
- 多租户数据隔离

## 常见问题
  1) 打开部署服务器的80 和 20011 端口，如果采用的是云服务器，需开放防火墙对这两个端口的访问限制
  2) 采用必要条件中之外其他版本的操作系统，安装dotnet-sdk-7.0时报错，请更换dpkg包的下载路径
  3) sudo yarn &amp;&amp; sudo yarn build 时报错，注意更改源，建议采用淘宝源

## 使用方法

  ```shell
  打开浏览器，进入：http://127.0.0.1 或者http://当前部署服务器的IP地址  
  
  初始账号: admin 密码: 1
  ```

## 版权信息
该项目使用的是 [Apache2.0](https://opensource.org/license/apache-2-0/) 协议.
