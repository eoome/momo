import http from '@/utils/http/request'
import { PageConfigProps } from '@/types/System/Form'
import { WarehouseProcessingVO, WarehouseProcessingDetailVO } from '@/types/WarehouseWorking/WarehouseProcessing'

// Get list
export const getStockProcessList = (data: PageConfigProps) => http({
    url: '/stockprocess/list',
    method: 'post',
    data
  })

// Get all
export const getStockProcessAll = () => http({
    url: '/stockprocess/all',
    method: 'get'
  })

// Get one
export const getStockProcessOne = (id: number) => http({
    url: '/stockprocess',
    method: 'get',
    params: {
      id
    }
  })

// Add a new form
export const addStockProcess = (data: WarehouseProcessingVO) => http({
    url: '/stockprocess',
    method: 'post',
    data
  })

// Update form
export const updateStockProcess = (data: WarehouseProcessingVO) => http({
    url: '/stockprocess',
    method: 'put',
    data
  })

// Delete form
export const deleteStockProcess = (id: number, logTemp: string) => http({
    url: '/stockprocess',
    method: 'delete',
    params: {
      id,
      logTemp
    }
  })

// Confirm process
export const confirmProcess = (id: number, logTemp: any) => http({
    url: '/stockprocess/process-confirm',
    method: 'put',
    params: {
      id,
      logTemp
    }
  })

// Confirm adjustment
export const confirmAdjustment = (id: number, logTemp: any) => http({
    url: '/stockprocess/adjustment-confirm',
    method: 'put',
    params: {
      id,
      logTemp
    }
  })
