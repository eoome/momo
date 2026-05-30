using ModernWMS.Core.Utility;
using System;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace ModernWMS.WMS.Entities.ViewModels.Dispatchlist
{
    /// <summary>
    /// 拣货明细
    /// </summary>
    public class PickingItemViewModel
    {
        #region constructor
        /// <summary>
        /// PickingItemViewModel
        /// </summary>
        public PickingItemViewModel()
        {
        }
        #endregion
        #region Property

        /// <summary>
        /// 规格标识
        /// </summary>
        [Display(Name = "sku_id")]
        public int sku_id { get; set; } = 0;

        public string sku_name { get; set; } = string.Empty;
        /// <summary>
        /// 货主名称
        /// </summary>
        public string goods_owner_name { get; set; } = string.Empty;

        /// <summary>
        /// 库区名称
        /// </summary>
        public string warehouse_area_name { get; set; } = string.Empty;

        /// <summary>
        /// 库位编码
        /// </summary>
        public string location_name { get; set; } = string.Empty;

        /// <summary>
        /// 待拣货数量
        /// </summary>
        [Display(Name = "pick_qty")]
        public int pick_qty { get; set; } = 0;

        /// <summary>
        /// 已拣货数量
        /// </summary>
        [Display(Name = "picked_qty")]
        public int picked_qty { get; set; } = 0;

        /// <summary>
        /// 商品编码
        /// </summary>
        public string spu_code { get; set; } = string.Empty;

        /// <summary>
        /// 商品名称
        /// </summary>
        public string spu_name { get; set; } = string.Empty;

        /// <summary>
        /// 商品描述
        /// </summary>
        public string spu_description { get; set; } = string.Empty;

        /// <summary>
        /// 商品条码
        /// </summary>
        public string bar_code { get; set; } = string.Empty;

        /// <summary>
        /// 规格编码
        /// </summary>
        public string sku_code { get; set; } = string.Empty;

        /// <summary>
        /// SN码
        /// </summary>
        [Display(Name = "series_number")]
        [MaxLength(64, ErrorMessage = "MaxLength")]
        public string series_number { get; set; } = string.Empty;

        /// <summary>
        /// 拣货人
        /// </summary>
        public string picker { get; set; } = string.Empty;

        public List<PickingItemDispatchViewModel> datalist { get; set; } = new List<PickingItemDispatchViewModel>();
        #endregion Property
    }
}
