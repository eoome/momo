<!-- Supplier Setting Import Dialog -->
<template>
  <v-dialog v-model="isShow" width="70%" transition="dialog-top-transition" :persistent="true">
    <template #default>
      <v-card>
        <v-toolbar color="white" :title="`${$t('system.page.import')}`"></v-toolbar>
        <v-card-text>
          <div class="mb-4">
            <tooltip-btn icon="mdi-plus" :tooltip-text="$t('system.page.chooseFile')" size="x-small" @click="method.chooseFile"></tooltip-btn>
            <tooltip-btn
              icon="mdi-export-variant"
              :tooltip-text="$t('system.page.exportTemplate')"
              size="x-small"
              @click="method.exportTemplate"
            ></tooltip-btn>
            <input v-show="false" id="open" ref="uploadExcel" type="file" accept=".xls, .xlsx" @change="method.readExcel" />
          </div>
          <vxe-table
            ref="xTable"
            :column-config="{ minWidth: '100px' }"
            :data="data.importData"
            :height="SYSTEM_HEIGHT.SELECT_TABLE"
            :edit-config="{ trigger: 'click', mode: 'cell' }"
            :edit-rules="data.validRules"
            :export-config="{}"
            align="center"
          >
            <template #empty>
              {{ i18n.global.t('system.page.noData') }}
            </template>
            <vxe-column type="seq" width="60"></vxe-column>
            <vxe-column field="operate" width="60" :title="$t('system.page.operate')" :resizable="false">
              <template #default="{ row }">
                <tooltip-btn
                  :flat="true"
                  icon="mdi-delete-outline"
                  :tooltip-text="$t('system.page.delete')"
                  :icon-color="errorColor"
                  @click="method.deleteRow(row)"
                ></tooltip-btn>
              </template>
            </vxe-column>
            <vxe-column field="image_url" :title="$t('base.commodityManagement.image')" width="100">
              <template #default="{ row }">
                <div class="image-cell">
                  <template v-if="row.image_url">
                    <div class="thumb-wrapper">
                      <img :src="`${BASE_URL}${row.image_url}`" class="thumb-img" />
                      <v-btn icon="mdi-close" size="x-small" variant="text" color="error" class="remove-btn" @click="method.removeImage(row)"></v-btn>
                    </div>
                  </template>
                  <template v-else>
                    <v-btn icon="mdi-upload" size="small" variant="outlined" @click="method.triggerImageUpload(row)"></v-btn>
                  </template>
                </div>
              </template>
            </vxe-column>
            <vxe-column field="spu_code" width="150px" :title="$t('base.commodityManagement.spu_code')">
            </vxe-column>
            <vxe-column field="spu_name" :title="$t('base.commodityManagement.spu_name')">
            </vxe-column>
            <vxe-column field="category_name" :title="$t('base.commodityManagement.category_name')">
            </vxe-column>
            <vxe-column field="spu_description" width="200" :title="$t('base.commodityManagement.spu_description')">
            </vxe-column>
            <vxe-column field="supplier_name" :title="$t('base.commodityManagement.supplier_name')">
            </vxe-column>
            <vxe-column field="brand" :title="$t('base.commodityManagement.brand')">
            </vxe-column>
            <vxe-column field="sku_code" width="150px" :title="$t('base.commodityManagement.sku_code')">
            </vxe-column>
            <vxe-column field="sku_name" :title="$t('base.commodityManagement.sku_name')">
            </vxe-column>
            <vxe-column field="bar_code" :title="$t('base.commodityManagement.bar_code')">
            </vxe-column>
            <vxe-column field="unit" :title="$t('base.commodityManagement.unit')">
            </vxe-column>
            <vxe-column field="weight" :title="$t('base.commodityManagement.weight')">
            </vxe-column>
            <vxe-column field="lenght" :title="$t('base.commodityManagement.lenght')">
            </vxe-column>
            <vxe-column field="width" :title="$t('base.commodityManagement.width')">
            </vxe-column>
            <vxe-column field="height" :title="$t('base.commodityManagement.height')">
            </vxe-column>
            <vxe-column field="cost" :title="$t('base.commodityManagement.cost')">
            </vxe-column>
            <vxe-column field="price" :title="$t('base.commodityManagement.price')">
            </vxe-column>
          </vxe-table>
        </v-card-text>
        <v-card-actions class="justify-end">
          <v-btn variant="text" @click="method.closeDialog">{{ $t('system.page.close') }}</v-btn>
          <v-btn color="primary" variant="text" @click="method.submit">{{ $t('system.page.submit') }}</v-btn>
        </v-card-actions>
      </v-card>
    </template>
  </v-dialog>
</template>

<script lang="ts" setup>
import { reactive, computed, ref, watch } from 'vue'
import { VxeTablePropTypes } from 'vxe-table'
import * as XLSX from 'xlsx'
import i18n from '@/languages/i18n'
import { hookComponent } from '@/components/system/index'
import { excelImport, submitImage, deleteImage } from '@/api/base/commodityManagementSetting'
import { SYSTEM_HEIGHT, errorColor } from '@/constant/style'
import tooltipBtn from '@/components/tooltip-btn.vue'
import { CommodityExcelVO, CommodityImportVO } from '@/types/Base/CommodityManagement'
import { exportData } from '@/utils/exportTable'
import { BASE_URL } from '@/constant/filePathBase'

const emit = defineEmits(['close', 'saveSuccess'])
const uploadExcel = ref()
const xTable = ref()

const props = defineProps<{
  showDialog: boolean
}>()

const isShow = computed(() => props.showDialog)

const data = reactive({
  importData: ref<Array<CommodityExcelVO>>([]),
  ExcelData: ref<Array<CommodityImportVO>>([]),
  tableData: [],
  validRules: ref<VxeTablePropTypes.EditRules>({})
})

const method = reactive({
  initForm: () => {
    data.importData = []
  },
  expandAllRows: () => {
    const expandRows = xTable.value.getTreeExpandRecords()
    const parentData = data.tableData.filter((item: any) => !item.parent_id)

    if (expandRows.length === parentData.length) {
      xTable.value.setAllTreeExpand(false)
    } else {
      xTable.value.setAllTreeExpand(true)
    }
  },
    // Trigger image upload
  triggerImageUpload: async (row: any) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.onchange = async (e: any) => {
      const file = e.target.files[0]
      if (!file) return
      try {
        // 假设 submitImage 返回 { data: { path: string } }
        const res = await submitImage(file)
        // 上传成功后把后端返回的路径赋值给 row.imagesPath
        row.image_url = res.data.data
      } catch (err) {
        hookComponent.$message({
          type: 'error',
          content: '上传失败，请重试'
        })
      }
    }
    input.click()
  },

  // Remove image
  removeImage: async (row: any) => {
    if (!row.image_url) return
    
    try {
      const { data: res } = await deleteImage(row.image_url)
      if (!res.isSuccess) {
        hookComponent.$message({
          type: 'error',
          content: res.errorMessage || '删除图片失败'
        })
        return
      }
      // 删除成功，前端置空
      row.image_url = ''
      hookComponent.$message({
        type: 'success',
        content: '图片已删除'
      })
    } catch (error) {
      hookComponent.$message({
        type: 'error',
        content: '删除图片请求失败'
      })
      console.error(error)
    }
  },
  closeDialog: () => {
    emit('close')
  },
  submit: async () => {
    const isValid = method.valid()
    if (!isValid) {
      return
    }

    const $table = xTable.value
    // It must be use 'getTableData()' to get all datas with table because it will delete row sometimes.
    const importData = $table.getTableData().fullData
    
    // 处理数据
    const spuMap = new Map<string, CommodityImportVO>()
    for (const [index, item] of importData.entries()) {
      // 检查必填字段是否存在
      if (
        !item.spu_code?.trim() || !item.spu_name?.trim() || !item.category_name?.trim() || !item.supplier_name?.trim() || !item.sku_code?.trim() || !item.sku_name?.trim() || !item.unit?.trim()
      ) {
        // 抛错
        hookComponent.$message({
          type: 'error',
          content: `${ i18n.global.t('system.tips.RequiredFieldsIsEmpty') }`
        })
        return
      }

      // 如果当前 spu 不存在，则先初始化
      if (!spuMap.has(item.spu_code)) {
        spuMap.set(item.spu_code, {
          id: index + 1,
          spu_code: item.spu_code,
          spu_name: item.spu_name,
          category_name: item.category_name,
          spu_description: item.spu_description,
          supplier_name: item.supplier_name,
          brand: item.brand,
          length_unit: 1,
          volume_unit: 0,
          weight_unit: 1,
          detailList: []
        })
      }

      // 获取当前 spu 的信息
      const spu = spuMap.get(item.spu_code)!

      // 数值单位提取
      const parseValueWithUnit = (val?: string) => {
        if (!val?.trim()) return { num: undefined, unit: undefined }
        const match = val.match(/^([\d.]+)\s*(\S*)$/)// 提取数字和单位
        if (match) {
          return {
            num: Number(match[1]),
            unit: match[2] || undefined
          }
        }
        return { num: undefined, unit: undefined }
      }

      // 单位映射函数
      const mapLengthUnit = (unit?: string) => {
        switch (unit) {
          case 'mm': return 0
          case 'cm': return 1
          case 'dm': return 2
          case 'm': return 3
          default: return 1
        }
      }

      const mapWeightUnit = (unit?: string) => {
        switch (unit) {
          case 'mg': return 0
          case 'g': return 1
          case 'kg': return 2
          default: return 1
        }
      }

      // 解析可能带单位的字段
      const weightParsed = parseValueWithUnit(item.weight)
      const lengthParsed = parseValueWithUnit(item.lenght)
      const widthParsed = parseValueWithUnit(item.width)
      const heightParsed = parseValueWithUnit(item.height)

      if (lengthParsed.unit) spu.length_unit = mapLengthUnit(lengthParsed.unit)
      if (widthParsed.unit) spu.length_unit = mapLengthUnit(widthParsed.unit)
      if (heightParsed.unit) spu.length_unit = mapLengthUnit(heightParsed.unit)
      if (weightParsed.unit) spu.weight_unit = mapWeightUnit(weightParsed.unit)

      // 添加 sku 信息到 detailList
      spu.detailList.push({
        id: spu.detailList.length + 1,
        sku_code: item.sku_code,
        image_url: item.image_url?.trim() ? item.image_url : undefined,
        sku_name: item.sku_name,
        bar_code: item.bar_code,
        unit: item.unit,
        cost: item.cost?.trim() ? Number(item.cost) : undefined,
        price: item.price?.trim() ? Number(item.price) : undefined,
        weight: weightParsed.num,
        lenght: lengthParsed.num,
        width: widthParsed.num,
        height: heightParsed.num
      })
    }

    const { data: res } = await excelImport(Array.from(spuMap.values()))
    if (!res.isSuccess) {
      hookComponent.$message({
        type: 'error',
        content: res.errorMessage
      })
      return
    }
    hookComponent.$message({
      type: 'success',
      content: `${ i18n.global.t('system.page.submit') }${ i18n.global.t('system.tips.success') }`
    })
    emit('saveSuccess')
    emit('close')
  },

  valid: () => {
    const $table = xTable.value
    const importData = $table.getTableData().fullData

    if (importData.length <= 0) {
      hookComponent.$message({
        type: 'error',
        content: `${ i18n.global.t('system.tips.detailLengthIsZero') }`
      })
      return false
    }
    return true
  },

  chooseFile: async () => {
    uploadExcel.value.value = ''
    uploadExcel.value.click()
  },

  readExcel: async (evnt: any) => {
    const files = evnt.target.files
    if (files.length <= 0) {
      return false
    }

    const file = files[0]
    const fileReader = new FileReader()

    fileReader.onload = (ev: ProgressEvent<FileReader>) => {
      const fileData = ev?.target?.result
      if (fileData) {
        const workbook = XLSX.read(fileData, { type: 'binary' })
        const wsname = workbook.SheetNames[0]

        let ws = XLSX.utils.sheet_to_json(workbook.Sheets[wsname])
        let str = JSON.stringify(ws)
        str = str.replace(/（/g, '(')
        str = str.replace(/）/g, ')')
        ws = JSON.parse(str)

        data.importData = []
        ws.forEach((value: any, index: number, ws: any) => {
          data.importData.push({
            spu_code: ws[index][i18n.global.t('base.commodityManagement.spu_code')] ? `${ ws[index][i18n.global.t('base.commodityManagement.spu_code')] }` : '',
            spu_name: ws[index][i18n.global.t('base.commodityManagement.spu_name')] ? `${ ws[index][i18n.global.t('base.commodityManagement.spu_name')] }` : '',
            category_name: ws[index][i18n.global.t('base.commodityManagement.category_name')] ? `${ ws[index][i18n.global.t('base.commodityManagement.category_name')] }` : '',
            sku_code: ws[index][i18n.global.t('base.commodityManagement.sku_code')] ? `${ ws[index][i18n.global.t('base.commodityManagement.sku_code')] }` : '',
            sku_name: ws[index][i18n.global.t('base.commodityManagement.sku_name')] ? `${ ws[index][i18n.global.t('base.commodityManagement.sku_name')] }` : '',
            unit: ws[index][i18n.global.t('base.commodityManagement.unit')] ? `${ ws[index][i18n.global.t('base.commodityManagement.unit')] }` : '',
            spu_description: ws[index][i18n.global.t('base.commodityManagement.spu_description')] ? `${ ws[index][i18n.global.t('base.commodityManagement.spu_description')] }` : '',
            supplier_name: ws[index][i18n.global.t('base.commodityManagement.supplier_name')] ? `${ ws[index][i18n.global.t('base.commodityManagement.supplier_name')] }` : '',
            brand: ws[index][i18n.global.t('base.commodityManagement.brand')] ? `${ ws[index][i18n.global.t('base.commodityManagement.brand')] }` : '',
            bar_code: ws[index][i18n.global.t('base.commodityManagement.bar_code')] ? `${ ws[index][i18n.global.t('base.commodityManagement.bar_code')] }` : '',
            weight: ws[index][i18n.global.t('base.commodityManagement.weight')] ? `${ ws[index][i18n.global.t('base.commodityManagement.weight')] }` : '',
            lenght: ws[index][i18n.global.t('base.commodityManagement.lenght')] ? `${ ws[index][i18n.global.t('base.commodityManagement.lenght')] }` : '',
            width: ws[index][i18n.global.t('base.commodityManagement.width')] ? `${ ws[index][i18n.global.t('base.commodityManagement.width')] }` : '',
            height: ws[index][i18n.global.t('base.commodityManagement.height')] ? `${ ws[index][i18n.global.t('base.commodityManagement.height')] }` : '',
            cost: ws[index][i18n.global.t('base.commodityManagement.cost')] ? `${ ws[index][i18n.global.t('base.commodityManagement.cost')] }` : '',
            price: ws[index][i18n.global.t('base.commodityManagement.price')] ? `${ ws[index][i18n.global.t('base.commodityManagement.price')] }` : ''
          })
        })
      }
    }
    fileReader.readAsBinaryString(file)
  },

  exportTemplate: () => {
    const $table = xTable.value
    exportData({
      table: $table,
      filename: i18n.global.t('router.sideBar.commodityManagement'),
      mode: 'header',
      columnFilterMethod({ column }: any) {
        return !['checkbox', 'seq'].includes(column?.type) && !['operate', 'image_url'].includes(column?.field)
      }
    })
  },

  deleteRow: (row: CommodityExcelVO) => {
    hookComponent.$dialog({
      content: i18n.global.t('system.tips.beforeDeleteDetailMessage'),
      handleConfirm: async () => {
        if (row) {
          const $table = xTable.value
          $table.remove(row)
        }
      }
    })
  }
})

watch(
  () => isShow.value,
  (val) => {
    if (val) {
      method.initForm()
    }
  }
)
</script>

<style scoped lang="less">
.v-form {
  div {
    margin-bottom: 7px;
  }
}
.image-cell {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 6px;

  .thumb-wrapper {
    position: relative;
    display: inline-block;
  }

  .thumb-img {
    width: 60px;
    height: 60px;
    object-fit: cover;
    border-radius: 4px;
    display: block;
  }

  .remove-btn {
    position: absolute;
    top: -6px;
    right: -6px;
    background-color: white;
    border-radius: 50%;
    min-width: 20px;
    height: 20px;
    padding: 0;
  }
}
</style>
