using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using ModernWMS.Core.Extentions;
using System;
using ModernWMS.Core.Filters;
namespace ModernWMS
{
    public class Startup
    {
        /// <summary>
        /// startup
        /// </summary>
        /// <param name="configuration">Config</param>
        public Startup(IConfiguration configuration)
        {
            Configuration = configuration;
        }

        public IConfiguration Configuration { get; }

        /// <summary>
        ///  register service 
        /// </summary>
        /// <param name="services">services</param>
        public void ConfigureServices(IServiceCollection services)
        {
            services.AddExtensionsService(Configuration);
            services.AddSingleton<IHttpContextAccessor, HttpContextAccessor>();
            services.AddScoped<ModernWMS.Core.Interfaces.IRequestLogger, ModernWMS.WMS.Services.RequestLogger>();
            services.AddScoped<ModernWMS.WMS.IServices.IActionLogService, ModernWMS.WMS.Services.ActionLogService>();
            services.AddScoped<ApiLogFilter>();
        }

        /// <summary>
        /// configure
        /// </summary>
        /// <param name="app">app</param>
        /// <param name="env">env</param>
        /// <param name="serviceProvider">serviceProvider</param>
        public void Configure(IApplicationBuilder app, IWebHostEnvironment env, IServiceProvider service_provider)
        {
            app.UseExtensionsConfigure(env, service_provider, Configuration);
        }
    }
}
