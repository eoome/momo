using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace ModernWMS.WMS.Entities.ViewModels.Dispatchlist
{
    /// <summary>
    /// 拣货单
    /// </summary>
    public class PickinglistViewModel
    {
        #region constructor
        /// <summary>
        /// PickinglistViewModel
        /// </summary>
        public PickinglistViewModel()
        {
        }
        #endregion

        #region Property
        /// <summary>
        /// 仓库名称
        /// </summary>
        public string warehouse_name { get; set; } = string.Empty;
        /// <summary>
        /// 仓库id
        /// </summary>
        public string warehouse_id { get; set; } = string.Empty;
        /// <summary>
        /// 拣货明细
        /// </summary>
        public List<PickingItemViewModel> pickingDetails { get; set; } = new List<PickingItemViewModel>();
        #endregion
    }
}
