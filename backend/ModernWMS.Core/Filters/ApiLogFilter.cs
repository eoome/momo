using Microsoft.AspNetCore.Mvc.Filters;
using Microsoft.AspNetCore.Mvc;
using NLog;
using System.Diagnostics;
using System.Threading.Tasks;

namespace ModernWMS.Core.Filters
{
    public class ApiLogFilter : IAsyncActionFilter
    {
        private static readonly ILogger _successLogger = LogManager.GetLogger("ApiSuccessLogger");
        private static readonly ILogger _errorLogger = LogManager.GetLogger("ApiErrorLogger");
        public async Task OnActionExecutionAsync(ActionExecutingContext context, ActionExecutionDelegate next)
        {
            var request = context.HttpContext.Request;
            var requestPath = request.Path;
            var method = request.Method;
            var url = $"{request.Scheme}://{request.Host}{request.Path}{request.QueryString}";
            var argsJson = Newtonsoft.Json.JsonConvert.SerializeObject(context.ActionArguments);

            var watch = Stopwatch.StartNew();
            ActionExecutedContext executedContext = await next();
            watch.Stop();
            var elapsedMs = watch.ElapsedMilliseconds;
            if (executedContext.Exception != null)
            {
                _errorLogger.Error(executedContext.Exception,
                    $"[Request] Path={requestPath}, Method={method}, Args={argsJson} |url:{url}|action:{context.ActionDescriptor.DisplayName} |Elapsed={elapsedMs}ms");
            }
            else
            {
                int statusCode = 0;
                object resultObj = null;
                if (executedContext.Result is ObjectResult objectResult)
                {
                    statusCode = objectResult.StatusCode ?? context.HttpContext.Response.StatusCode;
                    resultObj = objectResult.Value;
                }
                else
                {
                    statusCode = context.HttpContext.Response.StatusCode;
                }
                var resultJson = Newtonsoft.Json.JsonConvert.SerializeObject(resultObj);
                _successLogger.Info(
                    $"[Request] Path={requestPath}, Method={method}, Args={argsJson} |url:{url}|action:{context.ActionDescriptor.DisplayName} |StatusCode={statusCode} |Result={resultJson} |Elapsed={elapsedMs}ms");
            }
        }
    }
}
