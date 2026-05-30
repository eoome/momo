import i18n from '@/languages/i18n'

export const actionDict: any = {
  companySetting: ['save', 'delete', 'export'],
  userRoleSetting: ['save', 'delete', 'export'],
  roleMenu: [],
  userManagement: ['save', 'delete', 'import', 'export', 'resetPwd', 'exportAll'],
  commodityCategorySetting: ['save', 'delete', 'export'],
  commodityManagement: ['save', 'delete', 'export', 'saftyStock', 'printQrCode', 'printBarCode', 'import', 'exportAll'],
  supplier: ['save', 'delete', 'import', 'export', 'exportAll'],
  print: ['save', 'delete', 'export', 'exportAll'],
  warehouseSetting: [
    'warehouse-save',
    'warehouse-delete',
    'warehouse-import',
    'warehouse-export',
    'warehouse-exportAll',
    'area-save',
    'area-delete',
    'area-export',
    'area-exportAll',
    'location-save',
    'location-delete',
    'location-export',
    'location-exportAll',
    'location-printBarCode',
    'location-printQrCode'
  ],
  ownerOfCargo: ['save', 'delete', 'import', 'export', 'exportAll'],
  freightSetting: ['save', 'delete', 'import', 'export', 'exportAll'],
  customer: ['save', 'delete', 'import', 'export', 'exportAll'],

  stockAsn: [
    'notice-save',
    'notice-delete',
    'notice-export',
    'notice-exportAll',
    'notice-printQrCode',
    'putOnTheShelf-printQrCode',
    'delivered-confirm',
    'delivered-export',
    'delivered-exportAll',
    'unloaded-confirm',
    'unloaded-delete',
    'unloaded-export',
    'unloaded-exportAll',
    'sorted-editCount',
    'sorted-confirm',
    'sorted-delete',
    'sorted-export',
    'sorted-exportAll',
    'putOnTheShelf-editArrival',
    'putOnTheShelf-delete',
    'putOnTheShelf-export',
    'putOnTheShelf-exportAll',
    'detail-export',
    'detail-exportAll'
  ],

  stockManagement: ['area-export', 'stock-export', 'stock-exportAll', 'area-exportAll'],
  saftyStock: ['export', 'exportAll'],
  asnStatistic: ['export', 'exportAll'],
  deliveryStatistic: ['export', 'exportAll'],
  stockageStatistic: ['export', 'exportAll'],

  warehouseProcessing: ['split', 'group', 'confirmOpeartion', 'confirmAdjust', 'delete', 'export', 'exportAll'],
  warehouseMove: ['save', 'delete', 'export', 'confirm', 'exportAll'],
  warehouseFreeze: ['freeze', 'unfreeze', 'export', 'exportAll'],
  warehouseAdjust: ['export', 'exportAll'],
  warehouseTaking: ['save', 'delete', 'export', 'confirmOpeartion', 'confirmAdjust', 'exportAll'],

  deliveryManagement: [
    'invoice-save',
    'invoice-confirm',
    'invoice-revoke',
    'invoice-delete',
    'invoice-export',
    'invoice-exportAll',
    'invoice-printQrCode',
    'picked-confirm',
    'picked-revoke',
    'picked-export',
    'picked-exportAll',
    'picked-pick',
    'packaged-package',
    'packaged-export',
    'packaged-exportAll',
    'packaged-revoke',
    'weighed-weigh',
    'weighed-export',
    'weighed-exportAll',
    'weighed-revoke',
    'delivered-delivery',
    'delivered-setCarrier',
    'delivered-signIn',
    'delivered-export',
    'delivered-exportAll',
    'signedIn-export',
    'signedIn-exportAll'
  ]
}

// Get operation name
export const getActionName = (item: string, menu_name?: string) => {
  let titleKey = item

  let titleFun = ''
  if (titleKey.includes('-')) {
    titleFun = `${ i18n.global.t(`base.roleMenu.opeartionFunctionName.${ menu_name }.${ titleKey.split('-')[0] }`) }-`

    titleKey = titleKey.split('-')[1]
  }

  return `${ titleFun }${ i18n.global.t(`base.roleMenu.operationTitle.${ titleKey }`) }`
}
