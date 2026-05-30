<template>
  <v-dialog v-model="data.showDialog" :width="'70%'" transition="dialog-top-transition" :persistent="true">
    <template #default>
      <v-card class="formCard">
        <v-toolbar color="white" :title="`${$t('wms.deliveryManagement.pickListDetail')}`"></v-toolbar>
        <v-card-text>
          <div id="printArea">
            <vxe-table
              ref="xTable"
              keep-source
              :column-config="{ minWidth: '100px' }"
              :data="data.tableData"
              :height="'500px'"
              :span-method="mergeCells"
              border
              align="center"
            >
              <template #empty>
                {{ i18n.global.t('system.page.noData') }}
              </template>
              <vxe-column type="seq" width="60"></vxe-column>
              <vxe-column field="warehouse_name" :title="$t('wms.stockLocation.warehouse_name')"></vxe-column>
              <vxe-column field="spu_code" :title="$t('wms.deliveryManagement.spu_code')"></vxe-column>
              <vxe-column field="spu_name" :title="$t('wms.deliveryManagement.spu_name')"></vxe-column>
              <vxe-column field="sku_code" :title="$t('wms.deliveryManagement.sku_code')"></vxe-column>
              <vxe-column field="sku_name" :title="$t('wms.deliveryManagement.sku_name')"></vxe-column>
              <vxe-column field="series_number" :title="$t('wms.stockLocation.series_number')"></vxe-column>
              <vxe-column field="goods_owner_name" :title="$t('base.ownerOfCargo.goods_owner_name')"></vxe-column>
              <vxe-column field="warehouse_area_name" :title="$t('base.warehouseSetting.area_name')"></vxe-column>
              <vxe-column field="location_name" :title="$t('base.warehouseSetting.location_name')"></vxe-column>
              <vxe-column field="unpicked_qty" :title="$t('wms.deliveryManagement.unpicked_qty')"></vxe-column>
              <vxe-column :title="$t('wms.deliveryManagement.related_orders')" width="400">
                <template #default="{ row }">
                  <vxe-table
                    :data="row.related_orders"
                    border
                    size="mini"
                    :show-header="true"
                    :column-config="{ minWidth: '100px' }"
                  >
                    <vxe-column field="customer_name" :title="$t('wms.deliveryManagement.customer_name')"></vxe-column>
                    <vxe-column field="dispatch_no" :title="$t('wms.deliveryManagement.dispatch_no')"></vxe-column>
                    <vxe-column field="qty" :title="$t('wms.deliveryManagement.qty')"></vxe-column>
                  </vxe-table>
                </template>
              </vxe-column>
            </vxe-table>
          </div>
        </v-card-text>
        <v-card-actions class="justify-end">
          <v-btn variant="text" @click="method.closeDialog">{{ $t('system.page.close') }}</v-btn>
          <v-btn color="primary" variant="text" @click="method.printTable">{{ $t('system.page.print') }}</v-btn>
        </v-card-actions>
      </v-card>
    </template>
  </v-dialog>
</template>

<script lang="ts" setup>
import { ref, reactive } from 'vue'
import { hookComponent } from '@/components/system'
import { getPickDetail } from '@/api/wms/deliveryManagement'
import i18n from '@/languages/i18n'

const xTable = ref()

const data = reactive({
  showDialog: false,
  tableData: [] as any[]
})

const mergeCells = ({ rowIndex, column }) => {
  if (column.field === 'warehouse_name') {
    let rowspan = 1
    for (let i = rowIndex + 1; i < data.tableData.length; i++) {
      if (data.tableData[i].warehouse_name === data.tableData[rowIndex].warehouse_name) {
        rowspan++
      } else {
        break
      }
    }
    if (rowIndex > 0 && data.tableData[rowIndex].warehouse_name === data.tableData[rowIndex - 1].warehouse_name) {
      return { rowspan: 0, colspan: 0 }
    }
    return { rowspan, colspan: 1 }
  }
}

const method = reactive({
  getPickListDetail: async (items: any[]) => {
    const { data: res } = await getPickDetail(items)
    if (!res.isSuccess) {
      hookComponent.$message({
        type: 'error',
        content: res.errorMessage
      })
     return
    }

    const temp = res.data.flatMap((warehouse: any) => (
      warehouse.pickingDetails.map((pickingDetails: any) => ({
        warehouse_name: warehouse.warehouse_name,
        spu_code: pickingDetails.spu_code,
        spu_name: pickingDetails.spu_name,
        sku_code: pickingDetails.sku_code,
        sku_name: pickingDetails.sku_name,
        goods_owner_name: pickingDetails.goods_owner_name,
        warehouse_area_name: pickingDetails.warehouse_area_name,
        location_name: pickingDetails.location_name,
        unpicked_qty: pickingDetails.pick_qty,
        series_number: pickingDetails.series_number,
        related_orders: pickingDetails.datalist?.map(order => ({
          customer_name: order.customer_name,
          dispatch_no: order.dispatch_no,
          qty: order.qty
        }))
      }))))

    return temp
  },

  printTable: () => {
    const xTable = document.querySelector('#printArea .vxe-table') as HTMLElement
    if (!xTable) return
    const cloneTable = xTable.cloneNode(true) as HTMLElement
    cloneTable.querySelectorAll('.vxe-table--loading, .vxe-table--empty-content').forEach(el => el.remove())
    const iframe = document.createElement('iframe')
    iframe.style.position = 'absolute'
    iframe.style.width = '0'
    iframe.style.height = '0'
    iframe.style.border = 'none'
    document.body.appendChild(iframe)
    const doc = iframe.contentWindow?.document
    if (doc) {
      doc.open()
      doc.write(`
        <html>
          <head>
            <title>拣货单明细</title>
            <style>
              body { font-size: 14px; text-align: center; }
              table { border-collapse: collapse; width: 100%; }
              th, td { border: 1px solid #000; padding: 4px; text-align: center; vertical-align: middle; font-size: 16px;}
            </style>
          </head>
          <body>
            ${ cloneTable.outerHTML }
          </body>
        </html>
      `)
      doc.close()
      iframe.contentWindow?.focus()
      iframe.contentWindow?.print()
    }
    setTimeout(() => {
      document.body.removeChild(iframe)
    }, 1000)
  },

  openDialog: async (items: any[]) => {
    data.showDialog = true
    try {
      const response = await method.getPickListDetail(items)
      data.tableData = response
    } catch (err) {
      console.error(err)
      hookComponent.$message({
        type: 'error',
        content: '处理数据失败'
      })
    }
  },

  closeDialog: () => {
    data.showDialog = false
  }
})

defineExpose({
  openDialog: method.openDialog,
  closeDialog: method.closeDialog
})
</script>

<style scoped lang="less">

</style>
