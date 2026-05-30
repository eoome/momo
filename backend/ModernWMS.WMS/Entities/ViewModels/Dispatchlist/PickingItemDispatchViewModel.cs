using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace ModernWMS.WMS.Entities.ViewModels.Dispatchlist
{
    public class PickingItemDispatchViewModel
    {
        #region constructor
        /// <summary>
        /// PickingItemDispatchViewModel
        /// </summary>
        public PickingItemDispatchViewModel()
        {
        }
        #endregion
        #region  Property
        /// <summary>
        /// 客户id
        /// </summary>
        public string customer_name { get; set; } = string.Empty;
        /// <summary>
        /// 发货单号
        /// </summary>
        public string dispatch_no { get; set; } = string.Empty;
        /// <summary>
        /// 订单数量
        /// </summary>
        public int qty { get; set; } = 0;
        #endregion
    }
}
