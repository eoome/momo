using ModernWMS.Core.Interfaces;
using ModernWMS.WMS.IServices;
using ModernWMS.Core.Utility;
using Microsoft.AspNetCore.Http;
using System.Linq;
using System.Threading.Tasks;

namespace ModernWMS.WMS.Services
{
    /// <summary>
    /// RequestLogger
    /// </summary>
    public class RequestLogger : IRequestLogger
    {
        private readonly IActionLogService _actionLogService;
        private readonly IHttpContextAccessor _httpContextAccessor;
        /// <summary>
        /// RequestLogger
        /// </summary>
        /// <param name="actionLogService"></param>
        /// <param name="httpContextAccessor"></param>
        public RequestLogger(IActionLogService actionLogService, IHttpContextAccessor httpContextAccessor)
        {
            _actionLogService = actionLogService;
            _httpContextAccessor = httpContextAccessor;
        }
        /// <summary>
        /// LogAsync
        /// </summary>
        /// <param name="vuePath"></param>
        /// <param name="actionContent"></param>
        /// <returns></returns>
        public async Task LogAsync(string vuePath, string actionContent)
        {
            var user = new Core.JWT.CurrentUser();
            var httpContext = _httpContextAccessor.HttpContext;
            if (httpContext != null && httpContext.User?.Claims.Any() == true)
            {
                var claim = httpContext.User.Claims.FirstOrDefault(c => c.Type == "json");
                if (claim != null)
                    user = JsonHelper.DeserializeObject<Core.JWT.CurrentUser>(claim.Value);
            }
            await _actionLogService.AddLogAsync(vuePath, actionContent, user);
        }
    }
}
