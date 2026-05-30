using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace ModernWMS.Core.Interfaces
{
    /// <summary>
    /// General request log interface
    /// </summary>
    public interface IRequestLogger
    {
        /// <summary>
        /// Write request logs
        /// </summary>
        /// <param name="vuePath">vuePath</param>
        /// <param name="actionContent">actionContent</param>
        Task LogAsync(string vuePath, string actionContent);
    }
}

