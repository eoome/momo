// 日志处理
export function parseOperation(config): string {
    let str = ''
    const URL = config.url
    const REQ_METHOD = config.method
    const RES = config.data || config.params
    if (URL === '/company') {
        if (REQ_METHOD === 'post') {
            str = `[新增] 名称为${ RES.company_name }的公司`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 名称为${ RES.company_name }的公司信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 名称为${ RES.logTemp }的公司`
        }
    } else if (URL === '/userrole') {
        if (REQ_METHOD === 'post') {
            str = `[新增] 名称为${ RES.role_name }的角色`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 名称为${ RES.role_name }的角色信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 名称为${ RES.logTemp }的角色`
        }
    } else if (URL === '/rolemenu') {
        if (REQ_METHOD === 'post') {
            str = `[新增] 名称为${ RES.role_name }的角色权限`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 名称为${ RES.role_name }的角色权限信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 名称为${ RES.logTemp }的角色权限`
        }
    } else if (URL === '/user') {
        if (REQ_METHOD === 'post') {
            str = `[新增] 名称为${ RES.user_name }的用户`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 名称为${ RES.user_name }的用户信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 名称为${ RES.logTemp }的用户`
        }
    } else if (URL === '/user/reset-pwd') {
        str = `[重置] 名称为${ RES.logTemp.join(', ') }的用户密码`
    } else if (URL === '/category') {
        if (REQ_METHOD === 'post') {
            str = `[新增] 名称为${ RES.category_name }的商品类别`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 名称为${ RES.category_name }的商品类别信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 名称为${ RES.logTemp }的商品类别`
        }
    } else if (URL === '/spu') {
        if (REQ_METHOD === 'post') {
            str = `[新增] 商品编号为${ RES.spu_name }的商品`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 商品编号为${ RES.spu_name }的商品信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 商品编号为${ RES.logTemp }的商品`
        }
    } else if (URL === '/spu/sku-safety-stock') {
        if (REQ_METHOD === 'put') {
            str = `[修改] 商品规格编号为${ RES.sku_id }的商品安全库存`
        }
    } else if (URL === '/supplier') {
        if (REQ_METHOD === 'post') {
            str = `[新增] 名称为${ RES.supplier_name }的供应商`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 名称为${ RES.supplier_name }的供应商信息`
        } else if (REQ_METHOD === 'delete') { 
            str = `[删除] 名称为${ RES.logTemp }的供应商`
        }
    } else if (URL === '/PrintSolution') {
        if (REQ_METHOD === 'post') {
            str = `[新增] 名称为${ RES.solution_name }的打印方案`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 名称为${ RES.solution_name }的打印方案信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 名称为${ RES.logTemp }的打印方案`
        }
    } else if (URL === '/goodsowner') {
        if (REQ_METHOD === 'post') {
            str = `[新增] 名称为${ RES.goods_owner_name }的货主`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 名称为${ RES.goods_owner_name }的货主信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 名称为${ RES.logTemp }的货主`
        }
    } else if (URL === '/freightfee') {
        if (REQ_METHOD === 'post') {
            str = `[新增] 名称为${ RES.carrier }的承运商从${ RES.departure_city }到${ RES.arrival_city }的运费信息`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 名称为${ RES.carrier }的承运商从${ RES.departure_city }到${ RES.arrival_city }的运费信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 名称为${ RES.logTemp.carrier }的承运商从${ RES.logTemp.departure }到${ RES.logTemp.arrival }的运费信息`
        }
    } else if (URL === '/customer') {
        if (REQ_METHOD === 'post') {
            str = `[新增] 名称为${ RES.customer_name }的客户`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 名称为${ RES.customer_name }的客户信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 名称为${ RES.logTemp }的客户`
        }
    } else if (URL === '/warehouse') {
        if (REQ_METHOD === 'post') {
            str = `[新增] 名称为${ RES.warehouse_name }的仓库`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 名称为${ RES.warehouse_name }的仓库信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 名称为${ RES.logTemp }的仓库`
        }
    } else if (URL === '/warehousearea') {
        if (REQ_METHOD === 'post') {
            str = `[新增] ${ RES.warehouse_name }仓库中的名称为${ RES.area_name }的库区`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] ${ RES.warehouse_name }仓库中的名称为${ RES.area_name }的库区信息`
        } else if (REQ_METHOD === 'delete') {  
            str = `[删除] ${ RES.logTemp.warehouse }仓库中的名称为${ RES.logTemp.area }的库区`
        }
    } else if (URL === '/goodslocation') {
        if (REQ_METHOD === 'post') {
            str = `[新增] ${ RES.warehouse_name }仓库中${ RES.warehouse_area_name }库区下的编码为${ RES.location_name }的库位`
        } else if (REQ_METHOD === 'put') {
            str = `[修改] ${ RES.warehouse_name }仓库中${ RES.warehouse_area_name }库区下的编码为${ RES.location_name }的库位信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] ${ RES.logTemp.warehouse }仓库中${ RES.logTemp.area }库区的编码为${ RES.logTemp.location }的库位`
        }
    } else if (URL === '/stockprocess') {
        if (REQ_METHOD === 'post') {
            str = '[新增] 一份仓内加工的作业'
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 作业单号为${ RES.process_code }的作业信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 作业单号为${ RES.logTemp }的作业`
        }
    } else if (URL === '/stockprocess/process-confirm') {
        str = `[确认] 作业单号为${ RES.logTemp }的作业加工`
    } else if (URL === '/stockprocess/adjustment-confirm') {
        str = `[确认] 作业单号为${ RES.logTemp }的作业调整`
    } else if (URL === '/stockmove') {
        if (REQ_METHOD === 'post') {
            str = '[新增] 一份库存移动的作业'
        } else if (REQ_METHOD === 'put') {
            str = `[确认] 作业单号为${ RES.logTemp }的移库`
        } else if (REQ_METHOD === 'delete') {  
            str = `[删除] 作业单号为${ RES.logTemp }的移库作业`
        }
    } else if (URL === '/stockfreeze') {
        if (REQ_METHOD === 'post') {
            if (RES.job_type) {
                str = `[冻结] 一份商品编号为${ RES.spu_code }，规格编号为${ RES.sku_code }的库存`
            } else {
                str = `[解冻] 一份商品编号为${ RES.spu_code }，规格编号为${ RES.sku_code }的库存`
            }
        }
    } else if (URL === '/stocktaking') {
        if (REQ_METHOD === 'post') {
            str = '[新增] 一份库存盘点的作业'
        } else if (REQ_METHOD === 'put') {
            str = `[确认] 作业单号为${ RES.job_code }的库存盘点信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 作业单号为${ RES.logTemp }的库存盘点作业`
        }
    } else if (URL === '/stocktaking/adjustment-confirm') {
        str = `[确认] 作业单号为${ RES.logTemp }的库存盘点调整`
    } else if (URL === '/asn/asnmaster') {
        if (REQ_METHOD === 'post') {
            str = '[新增] 一条到货通知'
        } else if (REQ_METHOD === 'put') {
            str = `[修改] 通知书编号为${ RES.asn_no }的到货通知信息`
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 通知书编号为${ RES.logTemp }的到货通知`
        }
    } else if (URL === '/asn/confirm') {
        const temp = RES.map(item => `通知书编号为${ item.asn_no }中的商品编号为${ item.spu_code }规格编号为${ item.sku_code }的商品`).join(', ')
        str = `[确认] ${ temp }的到货`
    } else if (URL === '/asn/confirm-cancel') {
        const temp = config.logTemp.map(item => `通知书编号为${ item.asn_no }中的商品编号为${ item.spu_code }规格编号为${ item.sku_code }的商品`).join(', ')
        str = `[撤销] ${ temp }的到货`
    } else if (URL === '/asn/unload') {
        const temp = RES.map(item => `通知书编号为${ item.asn_no }中的商品编号为${ item.spu_code }规格编号为${ item.sku_code }的商品`).join(', ')
        str = `[确认] ${ temp }的卸货`
    } else if (URL === '/asn/unload-cancel') {
        const temp = config.logTemp.map(item => `通知书编号为${ item.asn_no }中的商品编号为${ item.spu_code }规格编号为${ item.sku_code }的商品`).join(', ')
        str = `[撤销] ${ temp }的卸货`
    } else if (URL === '/asn/sorted') {
        str = `[确认] 通知书编号为${ config.logTemp.asn_no }中的商品编号为${ config.logTemp.spu_code }规格编号为${ config.logTemp.sku_code }的商品的分拣`
    } else if (URL === '/asn/sorted-cancel') {
        const temp = config.logTemp.map(item => `通知书编号为${ item.asn_no }中的商品编号为${ item.spu_code }规格编号为${ item.sku_code }的商品`).join(', ')
        str = `[撤销] ${ temp }的分拣`
    } else if (URL === '/asn/putaway') {
        str = `[确认] 通知书编号为${ config.logTemp.asn_no }中的商品编号为${ config.logTemp.spu_code }规格编号为${ config.logTemp.sku_code }的商品的上架`
    } else if (URL === '/dispatchlist') {
        if (REQ_METHOD === 'post') {
            str = '[新增] 一条发货单'
        } else if (REQ_METHOD === 'delete') {
            str = `[删除] 发货单号为${ RES.dispatch_no }的发货单`
        }
    } else if (URL === '/dispatchlist/confirm-order') {
        str = `[确认] 发货单号为${ RES[0].dispatch_no }的商品发货`
    } else if (URL === '/dispatchlist/cancel-order') {
        if (RES.dispatch_status === 2) {
            str = `[撤销] 发货单号为${ RES.dispatch_no }的商品发货`
        } else if (RES.dispatch_status === 3) {
            str = `[撤销] 发货单号为${ RES.dispatch_no }的商品拣货`
        } else {
            str = `[撤销] 发货单号为${ RES.logTemp }的商品的打包/称重`
        }
    } else if (URL === '/dispatchlist/confirm-pick-dispatchlistno') {
        str = `[确认] 发货单号为${ RES.dispatch_no }的商品拣货`
    } else if (URL === '/dispatchlist/package') {
        const temp = RES.map(item => `发货单号为${ item.dispatch_no }的商品`).join(', ')
        str = `[确认] ${ temp }的打包`
    } else if (URL === '/dispatchlist/weight') {
        const temp = RES.map(item => `发货单号为${ item.dispatch_no }的商品`).join(', ')
        str = `[确认] ${ temp }的称重`
    } else if (URL === '/dispatchlist/delivery') {
        const temp = RES.map(item => `发货单号为${ item.dispatch_no }的商品`).join(', ')
        str = `[确认] ${ temp }的出库`
    } else if (URL === '/dispatchlist/sign') {
        const temp = RES.map(item => `发货单号为${ item.dispatch_no }的商品`).join(', ')
        str = `[确认] ${ temp }的签收`
    } else if (URL === '/user/excel') {
        const temp = RES.map(item => `${ item.user_name }`).join(', ')
        str = `[新增] 名称为${ temp }的用户`
    } else if (URL === '/spu/addlist') {
        const temp = RES.map(item => `${ item.spu_code }`).join(', ')
        str = `[新增] 商品编号为${ temp }的商品`
    } else if (URL === '/supplier/excel') {
        const temp = RES.map(item => `${ item.supplier_name }`).join(', ')
        str = `[新增] 名称为${ temp }的供应商`
    } else if (URL === '/warehouse/excel') {
        const temp = RES.map(item => `${ item.warehouse_name }`).join(', ')
        str = `[新增] 名称为${ temp }的仓库`
    } else if (URL === '/goodsowner/excel') {
        const temp = RES.map(item => `${ item.goods_owner_name }`).join(', ')
        str = `[新增] 名称为${ temp }的货主`
    } else if (URL === '/freightfee/excel') {
        const temp = RES.map(item => `名称为${ item.carrier }的承运商从${ item.departure_city }到${ item.arrival_city }`).join(', ')
        str = `[新增] ${ temp }的运费信息`
    } else if (URL === '/customer/excel') {
        const temp = RES.map(item => `${ item.customer_name }`).join(', ')
        str = `[新增] 名称为${ temp }的客户`
    }
    return str
}