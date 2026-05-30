import { CommodityImportVO } from './../../types/Base/CommodityManagement';
import http from '@/utils/http/request'
import { PageConfigProps } from '@/types/System/Form'
import { CommodityVO, UpdateSaftyStockReqBodyVO } from '@/types/Base/CommodityManagement'

// Find Data by Pagination
export const getSpuList = (data: PageConfigProps) => http({
    url: '/spu/list',
    method: 'post',
    data
  })

// Add a new form
export const addSpu = (data: CommodityVO) => http({
    url: '/spu',
    method: 'post',
    data
  })

// Update form
export const updateSpu = (data: CommodityVO) => http({
    url: '/spu',
    method: 'put',
    data
  })

// Delete form
export const deleteSpu = (id: number, logTemp:string) => http({
    url: '/spu',
    method: 'delete',
    params: {
      id,
      logTemp
    }
  })

// Update safety stock
export const updateSaftyStock = (data: { sku_id: number; detailList: UpdateSaftyStockReqBodyVO[] }) => http({
    url: '/spu/sku-safety-stock',
    method: 'put',
    data
  })

// Import commodity data from Excel
export const excelImport = (data: Array<CommodityImportVO>) => http({
    url: '/spu/addlist',
    method: 'post',
    data
  })

// Submit image for commodity
export const submitImage = (data: File) => {
  const formData = new FormData()
  formData.append('img', data)
  return http({
    url: '/spu/uploadimg',
    method: 'post',
    data: formData
  })
}

// Submit image for commodity
export const deleteImage = (imageUrl: string) => http({
    url: '/spu/deleteimg',
    method: 'delete',
    params: {
      imageUrl
    }
  })