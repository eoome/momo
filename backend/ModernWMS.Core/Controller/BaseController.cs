using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using ModernWMS.Core.JWT;
using ModernWMS.Core.Utility;
using System.Linq;
using NLog;
using ModernWMS.Core.Filters;

namespace ModernWMS.Core.Controller
{
    /// <summary>
    /// base controller
    /// </summary>
    [Authorize]
    [Produces("application/json")]
    [ServiceFilter(typeof(ApiLogFilter))]
    public class BaseController : ControllerBase
    {
        private static readonly ILogger _logger = LogManager.GetCurrentClassLogger();
        /// <summary>
        /// current user
        /// </summary>
        public CurrentUser CurrentUser
        {
            get
            {
                if (User != null && User.Claims.ToList().Count > 0)
                {
                    var Claim = User.Claims.First(claim => claim.Type == ClaimValueTypes.Json);
                    return Claim == null ? new CurrentUser() : JsonHelper.DeserializeObject<CurrentUser>(Claim.Value);
                }
                else
                {
                    return new CurrentUser();
                }
            }
        }

        public BaseController()
        {
            _logger.Info("BaseController initialized.");
        }
    }
}
