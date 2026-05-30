using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Newtonsoft.Json;
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using ModernWMS.Core.Models;
using ModernWMS.Core.Interfaces;

namespace ModernWMS.Core.Middleware
{
    /// <summary>
    /// Request response middleware
    /// </summary>
    public class RequestResponseMiddleware
    {
        #region parameter
        /// <summary>
        /// Delegate
        /// </summary>
        private readonly RequestDelegate _next;
        /// <summary>
        /// log manager
        /// </summary>
        private readonly ILogger<RequestResponseMiddleware> _logger;
        /// <summary>
        /// request Logger
        /// </summary>
        private readonly IRequestLogger _requestLogger;
        /// <summary>
        /// RequestResponseMiddleware
        /// </summary>
        /// <param name="next"></param>
        /// <param name="logger"></param>
        /// <param name="requestLogger"></param>
        public RequestResponseMiddleware(RequestDelegate next,
                                         ILogger<RequestResponseMiddleware> logger,
                                         IRequestLogger requestLogger)
        {
            _next = next;
            _logger = logger;
            _requestLogger = requestLogger;
        }

        #endregion

        /// <summary>
        /// Invoke
        /// </summary>
        /// <param name="context">httpcontext</param>
        /// <returns></returns>
        public async Task Invoke(HttpContext context)
        {
            if (!ModernWMS.Core.Utility.GlobalConsts.IsRequestResponseMiddleware)
            {
                await _next(context);
                return;
            }

            string requestInfo = "", responseInfo = "";
            var originalBodyStream = context.Response.Body;
            var stopwatch = Stopwatch.StartNew();
            try
            {
                requestInfo = await FormatRequest(context.Request);

                using (var responseBody = new MemoryStream())
                {
                    context.Response.Body = responseBody;

                    await _next(context);
                    stopwatch.Stop();

                    responseInfo = await FormatResponse(context.Response);
      
                    await responseBody.CopyToAsync(originalBodyStream);
                }
                string vuePath = context.Request.Headers["X-Vue-Path"].FirstOrDefault() ?? "";
                string encodedActionContent = context.Request.Headers["X-Action-Content"].FirstOrDefault() ?? "";
                string actionContent = string.IsNullOrEmpty(encodedActionContent)
                    ? ""
                    : System.Net.WebUtility.UrlDecode(encodedActionContent);

                if (!string.IsNullOrEmpty(vuePath) || !string.IsNullOrEmpty(actionContent))
                {
                    try
                    {
                        await _requestLogger.LogAsync(vuePath ?? "", actionContent ?? "");
                    }
                    catch (Exception ex)
                    {
                        _logger.LogWarning("Failed to record operation logs: " + ex.Message);
                    }
                }

                var logMsg = $@"request information: {requestInfo} ;time spent: {stopwatch.ElapsedMilliseconds}ms";
                _logger.LogInformation(logMsg);

            }
            catch (Exception ex)
            {
                stopwatch.Stop();
                var logMsg = $@"request information: {requestInfo}{Environment.NewLine}exception: {ex}{Environment.NewLine}time spent: {stopwatch.ElapsedMilliseconds}ms";
                _logger.LogError(logMsg);
                context.Response.StatusCode = 500;
                context.Response.ContentType = "application/json";
                string result = Utility.JsonHelper.SerializeObject(ResultModel<object>.Error(ex.Message));
                var bytes = Encoding.UTF8.GetBytes(result);
                await originalBodyStream.WriteAsync(bytes, 0, bytes.Length);
            }
        }
        /// <summary>
        /// FormatRequest
        /// </summary>
        /// <param name="request"></param>
        /// <returns></returns>
        private async Task<string> FormatRequest(HttpRequest request)
        {
            HttpRequestRewindExtensions.EnableBuffering(request);
            var buffer = new byte[Convert.ToInt32(request.ContentLength)];
            await request.Body.ReadAsync(buffer, 0, buffer.Length);
            var bodyAsText = Encoding.UTF8.GetString(buffer);
            request.Body.Seek(0, SeekOrigin.Begin);

            return $" {request.Method} {request.Scheme}://{request.Host}{request.Path} {request.QueryString} {bodyAsText}";
        }
        /// <summary>
        /// format response
        /// </summary>
        /// <param name="response">response</param>
        /// <returns></returns>
        private async Task<string> FormatResponse(HttpResponse response)
        {
            response.Body.Seek(0, SeekOrigin.Begin);
            var text = await new StreamReader(response.Body).ReadToEndAsync();
            response.Body.Seek(0, SeekOrigin.Begin);

            return $"{response.StatusCode}: {text}";
        }

    }
}
