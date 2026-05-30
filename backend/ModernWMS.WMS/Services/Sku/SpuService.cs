/*
 * date：2022-12-21
 * developer：AMo
 */
 using Mapster;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
 using Microsoft.AspNetCore.Mvc;
 using Microsoft.EntityFrameworkCore;
 using Microsoft.Extensions.Localization;
 using ModernWMS.Core.DBContext;
 using ModernWMS.Core.DynamicSearch;
 using ModernWMS.Core.JWT;
 using ModernWMS.Core.Models;
 using ModernWMS.Core.Services;
 using ModernWMS.WMS.Entities.Models;
 using ModernWMS.WMS.Entities.ViewModels;
 using ModernWMS.WMS.IServices;

namespace ModernWMS.WMS.Services
{
    /// <summary>
    ///  Spu Service
    /// </summary>
    public class SpuService : BaseService<SpuEntity>, ISpuService
    {
        #region Args
        /// <summary>
        /// The DBContext
        /// </summary>
        private readonly SqlDBContext _dBContext;

        /// <summary>
        /// Localizer Service
        /// </summary>
        private readonly IStringLocalizer<Core.MultiLanguage> _stringLocalizer;
        /// <summary>
        /// Web环境信息（用于获取wwwroot路径）
        /// </summary>
        private readonly IWebHostEnvironment _webHostEnvironment;
        #endregion
        #region nstants for image paths and helper methods
        /// <summary>
        /// 图片存储相对路径
        /// </summary>
        private readonly string[] _imageRelativePath = new[] { "sku_images" };

        /// <summary>
        /// 获取图片存储根目录
        /// </summary>
        /// <returns>图片存储根目录绝对路径</returns>
        private string GetImageStorageDirectory()
        {
            var directoryParts = new List<string> { _webHostEnvironment.WebRootPath }; // 使用wwwroot路径
            directoryParts.AddRange(_imageRelativePath); // 拼接子目录
            string fullPath = Path.Combine(directoryParts.ToArray());

            // 确保目录存在
            if (!Directory.Exists(fullPath))
            {
                Directory.CreateDirectory(fullPath);
            }
            return fullPath;
        }

        /// <summary>
        /// 从URL获取图片文件名
        /// </summary>
        /// <param name="imageUrl">图片URL</param>
        /// <returns>文件名</returns>
        private string GetFileNameFromUrl(string imageUrl)
        {
            if (string.IsNullOrEmpty(imageUrl))
                return string.Empty;

            // 从URL中提取文件名
            return Path.GetFileName(imageUrl);
        }

        /// <summary>
        /// 验证图片文件名格式
        /// </summary>
        /// <param name="fileName">文件名</param>
        /// <returns>是否有效</returns>
        private bool IsValidImageFileName(string fileName)
        {
            return !string.IsNullOrEmpty(fileName)
                   && fileName.StartsWith("sku-img_")
                   && Path.HasExtension(fileName);
        }
        #endregion
        #region constructor
        /// <summary>
        ///Spu  constructor
        /// </summary>
        /// <param name="dBContext">The DBContext</param>
        /// <param name="stringLocalizer">Localizer</param>
        public SpuService(
    SqlDBContext dBContext
  , IStringLocalizer<Core.MultiLanguage> stringLocalizer
  , IWebHostEnvironment webHostEnvironment // 新增参数
    )
        {
            this._dBContext = dBContext;
            this._stringLocalizer = stringLocalizer;
            this._webHostEnvironment = webHostEnvironment; // 赋值给私有字段
        }
        #endregion

        #region Api
        /// <summary>
        /// page search
        /// </summary>
        /// <param name="pageSearch">args</param>
        /// <param name="currentUser">currentUser</param>
        /// <returns></returns>
        public async Task<(List<SpuBothViewModel> data, int totals)> PageAsync(PageSearch pageSearch, CurrentUser currentUser)
        {
            ModernWMS.Core.DynamicSearch.QueryCollection queries = new ModernWMS.Core.DynamicSearch.QueryCollection();
            if (pageSearch.searchObjects.Any())
            {
                pageSearch.searchObjects.ForEach(s =>
                {
                    queries.Add(s);
                });
            }
            var Categorys = _dBContext.GetDbSet<CategoryEntity>();
            var Spus = _dBContext.GetDbSet<SpuEntity>();
            var Skus = _dBContext.GetDbSet<SkuEntity>();
            var SkuSafetyStocks = _dBContext.GetDbSet<SkuSafetyStockEntity>();
            var Warehouses = _dBContext.GetDbSet<WarehouseEntity>();
            var query = from m in Spus.AsNoTracking()
                        join c in Categorys.AsNoTracking() on m.category_id equals c.id
                        where m.tenant_id == currentUser.tenant_id
                        select new SpuBothViewModel
                        {
                            id = m.id,
                            spu_code = m.spu_code,
                            spu_name = m.spu_name,
                            category_id = m.category_id,
                            category_name = c.category_name,
                            spu_description = m.spu_code,
                            supplier_id = m.supplier_id,
                            supplier_name = m.supplier_name,
                            brand = m.brand,
                            origin = m.origin,
                            length_unit = m.length_unit,
                            volume_unit = m.volume_unit,
                            weight_unit = m.weight_unit,
                            creator = m.creator,
                            create_time = m.create_time,
                            last_update_time = m.last_update_time,
                            is_valid = m.is_valid,
                            detailList = Skus.AsNoTracking().Where(t => t.spu_id.Equals(m.id))
                                         .Select(t => new SkuViewModel
                                         {
                                             id = t.id,
                                             spu_id = t.spu_id,
                                             sku_code = t.sku_code,
                                             sku_name = t.sku_name,
                                             image_url = t.image_url,
                                             bar_code = t.bar_code,
                                             weight = t.weight,
                                             lenght = t.lenght,
                                             width = t.width,
                                             height = t.height,
                                             volume = t.volume,
                                             unit = t.unit,
                                             cost = t.cost,
                                             price = t.price,
                                             create_time = t.create_time,
                                             last_update_time = t.last_update_time,
                                             detailList = (from sss in SkuSafetyStocks.AsNoTracking()
                                                           join wh in Warehouses on sss.warehouse_id equals wh.id
                                                           where sss.sku_id.Equals(t.id)
                                                           select new SkuSafetyStockViewModel
                                                           {
                                                               id = sss.id,
                                                               sku_id = sss.sku_id,
                                                               safety_stock_qty = sss.safety_stock_qty,
                                                               warehouse_id = sss.warehouse_id,
                                                               warehouse_name = wh.warehouse_name
                                                           }).ToList()
                                         }).ToList()

                        };
            query = query.Where(queries.AsExpression<SpuBothViewModel>());
            int totals = await query.CountAsync();
            List<SpuBothViewModel> list;
            if (pageSearch.pageIndex <= 0 || pageSearch.pageSize <= 0)
            {
                list = await query.OrderByDescending(t => t.create_time).ToListAsync();
            }
            else
            {
                list = await query.OrderByDescending(t => t.create_time)
                                  .Skip((pageSearch.pageIndex - 1) * pageSearch.pageSize)
                                  .Take(pageSearch.pageSize)
                                  .ToListAsync();
            }
            return (list, totals);
        }

        /// <summary>
        /// Get a record by id
        /// </summary>
        /// <returns></returns>
        public async Task<SpuBothViewModel> GetAsync(int id)
        {
            var Categorys = _dBContext.GetDbSet<CategoryEntity>();
            var Spus = _dBContext.GetDbSet<SpuEntity>();
            var Skus = _dBContext.GetDbSet<SkuEntity>();
            var SkuSafetyStocks = _dBContext.GetDbSet<SkuSafetyStockEntity>();
            var Warehouses = _dBContext.GetDbSet<WarehouseEntity>();
            var query = from m in Spus.AsNoTracking()
                        join c in Categorys.AsNoTracking() on m.category_id equals c.id
                        where m.id == id
                        select new SpuBothViewModel
                        {
                            id = m.id,
                            spu_code = m.spu_code,
                            spu_name = m.spu_name,
                            category_id = m.category_id,
                            category_name = c.category_name,
                            spu_description = m.spu_description,
                            supplier_id = m.supplier_id,
                            supplier_name = m.supplier_name,
                            brand = m.brand,
                            origin = m.origin,
                            length_unit = m.length_unit,
                            volume_unit = m.volume_unit,
                            weight_unit = m.weight_unit,
                            creator = m.creator,
                            create_time = m.create_time,
                            last_update_time = m.last_update_time,
                            is_valid = m.is_valid,
                            detailList = Skus.Where(t => t.spu_id.Equals(m.id))
                                         .Select(t => new SkuViewModel
                                         {
                                             id = t.id,
                                             spu_id = t.spu_id,
                                             sku_code = t.sku_code,
                                             sku_name = t.sku_name,
                                             bar_code = t.bar_code,
                                             image_url = t.image_url,
                                             weight = t.weight,
                                             lenght = t.lenght,
                                             width = t.width,
                                             height = t.height,
                                             volume = t.volume,
                                             unit = t.unit,
                                             cost = t.cost,
                                             price = t.price,
                                             create_time = t.create_time,
                                             last_update_time = t.last_update_time,
                                             detailList = (from sss in SkuSafetyStocks.AsNoTracking()
                                                           join wh in Warehouses on sss.warehouse_id equals wh.id
                                                           where sss.sku_id.Equals(t.id)
                                                           select new SkuSafetyStockViewModel
                                                           {
                                                               id = sss.id,
                                                               sku_id = sss.sku_id,
                                                               safety_stock_qty = sss.safety_stock_qty,
                                                               warehouse_id = sss.warehouse_id,
                                                               warehouse_name = wh.warehouse_name
                                                           }).ToList()
                                         }).ToList()

                        };
            var data = await query.FirstOrDefaultAsync();
            if (data != null)
            {
                return data;
            }
            else
            {
                return new SpuBothViewModel();
            }
        }
        /// <summary>
        /// get sku info by sku_id
        /// </summary>
        /// <param name="sku_id">sku_id</param>
        /// <returns></returns>
        public async Task<SkuDetailViewModel> GetSkuAsync(int sku_id)
        {
            var Categorys = _dBContext.GetDbSet<CategoryEntity>();
            var Spus = _dBContext.GetDbSet<SpuEntity>();
            var Skus = _dBContext.GetDbSet<SkuEntity>();
            var query = from m in Spus.AsNoTracking()
                        join c in Categorys.AsNoTracking() on m.category_id equals c.id
                        join d in Skus.AsNoTracking() on m.id equals d.spu_id
                        where d.id == sku_id
                        select new SkuDetailViewModel
                        {  
                            spu_id = m.id,
                            spu_code = m.spu_code,
                            spu_name = m.spu_name,
                            category_id = m.category_id,
                            category_name = c.category_name,
                            spu_description = m.spu_description,
                            supplier_id = m.supplier_id,
                            supplier_name = m.supplier_name,
                            brand = m.brand,
                            origin = m.origin,
                            length_unit = m.length_unit,
                            volume_unit = m.volume_unit,
                            weight_unit = m.weight_unit,
                            sku_id = d.id,
                            sku_code = d.sku_code,
                            sku_name = d.sku_name,
                            bar_code = d.bar_code,
                            image_url = d.image_url,
                            weight = d.weight,
                            lenght = d.lenght,
                            width = d.width,
                            height = d.height,
                            volume = d.volume,
                            unit = d.unit,
                            cost = d.cost,
                            price = d.price
                        };
            var data = await query.FirstOrDefaultAsync();
            if (data != null)
            {
                return data;
            }
            else
            {
                return new SkuDetailViewModel();
            }

        }

        /// <summary>
        /// get sku info by bar_code
        /// </summary>
        /// <param name="bar_code">bar_code</param>
        /// <returns></returns>
        public async Task<SkuDetailViewModel> GetSkuByBarCodeAsync(string bar_code)
        {
            var Categorys = _dBContext.GetDbSet<CategoryEntity>();
            var Spus = _dBContext.GetDbSet<SpuEntity>();
            var Skus = _dBContext.GetDbSet<SkuEntity>();
            var query = from m in Spus.AsNoTracking()
                        join c in Categorys.AsNoTracking() on m.category_id equals c.id
                        join d in Skus.AsNoTracking() on m.id equals d.spu_id
                        where d.bar_code == bar_code
                        select new SkuDetailViewModel
                        {
                            spu_id = m.id,
                            spu_code = m.spu_code,
                            spu_name = m.spu_name,
                            category_id = m.category_id,
                            category_name = c.category_name,
                            spu_description = m.spu_description,
                            supplier_id = m.supplier_id,
                            supplier_name = m.supplier_name,
                            brand = m.brand,
                            origin = m.origin,
                            length_unit = m.length_unit,
                            volume_unit = m.volume_unit,
                            weight_unit = m.weight_unit,
                            sku_id = d.id,
                            sku_code = d.sku_code,
                            sku_name = d.sku_name,
                            bar_code = d.bar_code,
                            image_url = d.image_url,
                            weight = d.weight,
                            lenght = d.lenght,
                            width = d.width,
                            height = d.height,
                            volume = d.volume,
                            unit = d.unit,
                            cost = d.cost,
                            price = d.price
                        };
            var data = await query.FirstOrDefaultAsync();
            if (data != null)
            {
                return data;
            }
            else
            {
                return new SkuDetailViewModel();
            }

        }

        /// <summary>
        /// add a new record
        /// </summary>
        /// <param name="viewModel">viewmodel</param>
        /// <param name="currentUser">currentUser</param>
        /// <returns></returns>
        public async Task<(int id, string msg)> AddAsync(SpuBothViewModel viewModel, CurrentUser currentUser)
        {
            var DbSet = _dBContext.GetDbSet<SpuEntity>();
            if (await DbSet.AsNoTracking().AnyAsync(t => t.tenant_id.Equals(currentUser.tenant_id) && t.spu_code.Equals(viewModel.spu_code)))
            {
                return (0, string.Format(_stringLocalizer["exists_entity"], _stringLocalizer["spu_code"], viewModel.spu_code));
            }
            var entity = viewModel.Adapt<SpuEntity>();
            entity.id = 0;
            entity.creator = currentUser.user_name;
            entity.create_time = DateTime.Now;
            entity.last_update_time = DateTime.Now;
            entity.tenant_id = currentUser.tenant_id;
            if (viewModel.detailList.Any())
            {
                decimal dec = ChangeLengthUnit(entity.length_unit, entity.volume_unit);
                viewModel.detailList.ForEach(t =>
                {
                    t.id = 0;
                    t.volume = Math.Round(t.lenght * dec * t.width * dec * t.height * dec, 3);
                });
            }
            await DbSet.AddAsync(entity);
            await _dBContext.SaveChangesAsync();
            if (entity.id > 0)
            {
                return (entity.id, _stringLocalizer["save_success"]);
            }
            else
            {
                return (0, _stringLocalizer["save_failed"]);
            }
        }
        /// <summary>
        /// add new record list
        /// </summary>
        /// <param name="viewModels"></param>
        /// <param name="currentUser"></param>
        /// <returns></returns>
        public async Task<(int count, string msg)> AddListAsync(List<SpuBothViewModel> viewModels, CurrentUser currentUser)
        {
            if (viewModels == null || !viewModels.Any())
            {
                return (0, _stringLocalizer["batch_empty"]);
            }
            var dbSet = _dBContext.GetDbSet<SpuEntity>();
            var tenantId = currentUser.tenant_id;
            var spuCodes = viewModels.Select(vm => vm.spu_code?.Trim()).ToList();
            var invalidSpuCodes = viewModels.Where(vm => string.IsNullOrWhiteSpace(vm.spu_code?.Trim()))
                                            .Select((vm, idx) => $"第{idx + 1}条数据")
                                            .ToList();
            if (invalidSpuCodes.Any())
            {
                return (0, string.Format(_stringLocalizer["spu_code_required"], string.Join("、", invalidSpuCodes)));
            }
            var duplicateCodes = spuCodes
                .GroupBy(code => code)
                .Where(group => group.Count() > 1 && !string.IsNullOrEmpty(group.Key))
                .Select(group => group.Key)
                .ToList();
            if (duplicateCodes.Any())
            {
                return (0, string.Format(_stringLocalizer["batch_duplicate_spu_code"], string.Join(",", duplicateCodes)));
            }
            var existingCodes = await dbSet.AsNoTracking()
                .Where(t => t.tenant_id == tenantId && spuCodes.Contains(t.spu_code))
                .Select(t => t.spu_code)
                .ToListAsync();
            List<SpuBothViewModel> newVms = new();
            List<SpuBothViewModel> existingVms = new();
            List<string> inconsistentCodes = new();
            Dictionary<string, SpuEntity> existingSpuDict = new();
            if (existingCodes.Any())
            {
                existingSpuDict = await dbSet.AsNoTracking()
                    .Include(spu => spu.detailList)
                    .Where(t => t.tenant_id == tenantId && existingCodes.Contains(t.spu_code))
                    .ToDictionaryAsync(s => s.spu_code.Trim(), s => s);

                foreach (var vm in viewModels)
                {
                    var spuCode = vm.spu_code!.Trim();
                    if (existingSpuDict.ContainsKey(spuCode))
                    {
                        var existingSpu = existingSpuDict[spuCode];
                        bool isNameConsistent = string.Equals(
                            vm.spu_name?.Trim(),
                            existingSpu.spu_name?.Trim(),
                            StringComparison.OrdinalIgnoreCase
                        );
                        bool isSupplierConsistent = string.Equals(
                            vm.supplier_name?.Trim(),
                            existingSpu.supplier_name?.Trim(),
                            StringComparison.OrdinalIgnoreCase
                        );
                        if (!isNameConsistent || !isSupplierConsistent)
                        {
                            inconsistentCodes.Add(spuCode);
                        }
                        else
                        {
                            existingVms.Add(vm);
                        }
                    }
                    else
                    {
                        newVms.Add(vm);
                    }
                }
                if (inconsistentCodes.Any())
                {
                    return (0, string.Format(_stringLocalizer["spu_info_inconsistent"], string.Join(",", inconsistentCodes)));
                }
            }
            else
            {
                newVms = viewModels.ToList();
            }
            var allVms = newVms.Concat(existingVms).ToList();
            var supplierNames = allVms.Select(vm => vm.supplier_name?.Trim())
                                     .Where(name => !string.IsNullOrEmpty(name))
                                     .Distinct()
                                     .ToList();
            var categoryNames = allVms.Select(vm => vm.category_name?.Trim())
                                     .Where(name => !string.IsNullOrEmpty(name))
                                     .Distinct()
                                     .ToList();
            var existingSuppliers = await _dBContext.GetDbSet<SupplierEntity>().AsNoTracking()
                .Where(s => s.tenant_id == tenantId && supplierNames.Contains(s.supplier_name))
                .Select(s => new { s.supplier_name, s.id })
                .ToDictionaryAsync(key => key.supplier_name.Trim(), value => value.id);
            var existingCategories = await _dBContext.GetDbSet<CategoryEntity>().AsNoTracking()
                .Where(c => c.tenant_id == tenantId && categoryNames.Contains(c.category_name))
                .Select(c => new { c.category_name, c.id })
                .ToDictionaryAsync(key => key.category_name.Trim(), value => value.id);
            foreach (var vm in allVms)
            {
                var supplierName = vm.supplier_name?.Trim();
                if (string.IsNullOrEmpty(supplierName) || !existingSuppliers.TryGetValue(supplierName, out var supplierId))
                {
                    return (0, string.Format(_stringLocalizer["supplier_not_exists"], supplierName));
                }
                vm.supplier_id = supplierId;

                var categoryName = vm.category_name?.Trim();
                if (string.IsNullOrEmpty(categoryName) || !existingCategories.TryGetValue(categoryName, out var categoryId))
                {
                    return (0, string.Format(_stringLocalizer["category_not_exists"], categoryName));
                }
                vm.category_id = categoryId;
            }
            using (var transaction = await _dBContext.Database.BeginTransactionAsync())
            {
                try
                {
                    int totalAffected = 0;
                    foreach (var vm in existingVms)
                    {
                        var spuCode = vm.spu_code!.Trim();
                        var existingSpu = existingSpuDict[spuCode];
                        var skuDbSet = _dBContext.GetDbSet<SkuEntity>();
                        var newSkus = vm.detailList?.Select(skuVm =>
                        {
                            var sku = skuVm.Adapt<SkuEntity>();
                            sku.id = 0;
                            sku.spu_id = existingSpu.id;
                            decimal unitConvert = ChangeLengthUnit(existingSpu.length_unit, existingSpu.volume_unit);
                            sku.volume = Math.Round(
                                sku.lenght * unitConvert *
                                sku.width * unitConvert *
                                sku.height * unitConvert, 3);
                            return sku;
                        }).Where(sku => sku != null).ToList();
                        if (newSkus?.Any() ?? false)
                        {
                            var duplicateSkuCodes = newSkus
                                .GroupBy(s => s.sku_code?.Trim())
                                .Where(g => g.Count() > 1 && !string.IsNullOrEmpty(g.Key))
                                .Select(g => g.Key)
                                .ToList();
                            if (duplicateSkuCodes.Any())
                            {
                                return (0, string.Format(_stringLocalizer["duplicate_sku_in_batch"],
                                    spuCode, string.Join(",", duplicateSkuCodes)));
                            }
                            var existingSkuCodes = existingSpu.detailList?
                                .Select(s => s.sku_code?.Trim())
                                .Where(c => !string.IsNullOrEmpty(c))
                                .ToList() ?? new List<string>();
                            var conflictSkuCodes = newSkus
                                .Where(s => !string.IsNullOrEmpty(s.sku_code?.Trim()) &&
                                           existingSkuCodes.Contains(s.sku_code.Trim()))
                                .Select(s => s.sku_code!.Trim())
                                .ToList();
                            if (conflictSkuCodes.Any())
                            {
                                return (0, string.Format(_stringLocalizer["sku_code_exists"],
                                    spuCode, string.Join(",", conflictSkuCodes)));
                            }
                            await skuDbSet.AddRangeAsync(newSkus);
                            existingSpu.last_update_time = DateTime.Now;
                            dbSet.Update(existingSpu);

                            totalAffected += newSkus.Count;
                        }
                    }
                    if (newVms.Any())
                    {
                        var newSpuEntities = newVms.Select(vm =>
                        {
                            var entity = vm.Adapt<SpuEntity>();
                            entity.id = 0;
                            entity.creator = currentUser.user_name;
                            entity.create_time = DateTime.Now;
                            entity.last_update_time = DateTime.Now;
                            entity.tenant_id = tenantId;
                            if (entity.detailList?.Any() ?? false)
                            {
                                decimal unitConvert = ChangeLengthUnit(entity.length_unit, entity.volume_unit);
                                foreach (var sku in entity.detailList)
                                {
                                    sku.id = 0;
                                    sku.volume = Math.Round(
                                        sku.lenght * unitConvert *
                                        sku.width * unitConvert *
                                        sku.height * unitConvert, 3);
                                }
                            }
                            return entity;
                        }).ToList();

                        await dbSet.AddRangeAsync(newSpuEntities);
                        totalAffected += newSpuEntities.Count;
                    }
                    await _dBContext.SaveChangesAsync();
                    await transaction.CommitAsync();
                    return (totalAffected, _stringLocalizer["batch_save_success"]);
                }
                catch (Exception ex)
                {
                    await transaction.RollbackAsync();
                    return (0, string.Format(_stringLocalizer["batch_save_failed"], ex.Message));
                }
            }
        }
        /// <summary>
        /// 上传SKU图片（直接在方法中定义存储路径）
        /// </summary>
        /// <param name="img">图片文件</param>
        /// <param name="currentUser">当前用户信息</param>
        /// <returns>图片URL和操作消息</returns>
        public async Task<(string url, string msg)> UploadImg(IFormFile img, CurrentUser currentUser)
        {
            // 验证文件是否存在
            if (img == null || img.Length == 0)
            {
                return (string.Empty, _stringLocalizer["img_required"]);
            }
            try
            {
                // 验证文件类型（仅允许常见图片格式）
                var allowedContentTypes = new[] { "image/jpeg", "image/png", "image/gif", "image/bmp" };
                if (!allowedContentTypes.Contains(img.ContentType))
                {
                    return (string.Empty, _stringLocalizer["Unsupported image types, only JPG, PNG, GIF, BMP formats are allowed"]);
                }
                // 验证文件大小（限制5MB以内）
                var maxFileSize = 5 * 1024 * 1024; // 5MB
                if (img.Length > maxFileSize)
                {
                    return (string.Empty, string.Format(_stringLocalizer["The size of the image cannot be exceeded{0}MB"], maxFileSize / 1024 / 1024));
                }
                // 获取图片存储目录
                var uploadDir = GetImageStorageDirectory();
                // 确保目录存在
                if (!Directory.Exists(uploadDir))
                {
                    Directory.CreateDirectory(uploadDir);
                }

                // 生成唯一文件名
                var fileExtension = Path.GetExtension(img.FileName).ToLowerInvariant();
                var uniqueFileName = $"sku-img_{Guid.NewGuid()}{fileExtension}";
                var filePath = Path.Combine(uploadDir, uniqueFileName);
                // 保存文件
                using (var stream = new FileStream(filePath, FileMode.Create))
                {
                    await img.CopyToAsync(stream);
                }
                var imageUrl = $"/{string.Join("/", _imageRelativePath)}/{uniqueFileName}"; // 拼接为/assets/sku-images/文件名
                return (imageUrl, _stringLocalizer["Upload sucess"]);
            }
            catch (IOException)
            {
                return (string.Empty, _stringLocalizer["Upload failed"]);
            }
            catch (Exception ex)
            {
                return (string.Empty, string.Format(_stringLocalizer["Upload failed: {0}"], ex.Message));
            }
        }
        /// <summary>
        /// 删除SKU图片
        /// </summary>
        /// <param name="imageUrl">图片URL</param>
        /// <param name="currentUser">当前用户信息</param>
        /// <returns>操作结果和消息</returns>
        public async Task<(bool flag, string msg)> DeleteImg(string imageUrl, CurrentUser currentUser)
        {
            // 验证URL是否有效
            if (string.IsNullOrEmpty(imageUrl))
            {
                return (false, _stringLocalizer["image_url_required"]);
            }

            try
            {
                // 从URL获取文件名
                var fileName = GetFileNameFromUrl(imageUrl);

                // 验证文件名格式
                if (!IsValidImageFileName(fileName))
                {
                    return (false, _stringLocalizer["invalid_image_url"]);
                }

                // 获取图片存储目录并构建文件路径
                var uploadDir = GetImageStorageDirectory();
                var filePath = Path.Combine(uploadDir, fileName);

                // 检查文件是否存在
                if (!File.Exists(filePath))
                {
                    return (false, _stringLocalizer["image_file_not_found"]);
                }

                // 删除文件
                File.Delete(filePath);

                // 同步更新数据库中关联的图片路径
                var skuEntity = await _dBContext.GetDbSet<SkuEntity>()
                    .FirstOrDefaultAsync(s => s.image_url == imageUrl);

                if (skuEntity != null)
                {
                    skuEntity.image_url = null;
                    skuEntity.last_update_time = DateTime.Now;
                    await _dBContext.SaveChangesAsync();
                }

                return (true, _stringLocalizer["image_delete_success"]);
            }
            catch (IOException)
            {
                return (false, _stringLocalizer["image_delete_failed_file_in_use"]);
            }
            catch (Exception ex)
            {
                return (false, string.Format(_stringLocalizer["image_delete_failed: {0}"], ex.Message));
            }
        }


        /// change to the volume unit
        /// </summary>
        /// <param name="length_unit">length_unit</param>
        /// <param name="volume_unit">volume_unit</param>
        /// <returns></returns>
        private decimal ChangeLengthUnit(byte length_unit, byte volume_unit)
        {
            if (volume_unit.Equals(0)) // cm3
            {
                if (length_unit.Equals(0)) //mm
                {
                    return 0.1M;
                }
                else if (length_unit.Equals(2)) // dm
                {
                    return 10M;
                }
                else if (length_unit.Equals(3)) // m
                {
                    return 100M;
                }
                else // cm
                {
                    return 1M;
                }
            }
            else if (volume_unit.Equals(1)) // dm3
            {
                if (length_unit.Equals(0))
                {
                    return 0.01M;
                }
                else if (length_unit.Equals(2))
                {
                    return 1M;
                }
                else if (length_unit.Equals(3))
                {
                    return 10M;
                }
                else
                {
                    return 0.1M;
                }
            }
            else if (volume_unit.Equals(2)) // m3
            {
                if (length_unit.Equals(0))
                {
                    return 0.001M;
                }
                else if (length_unit.Equals(2))
                {
                    return 0.1M;
                }
                else if (length_unit.Equals(3))
                {
                    return 1M;
                }
                else
                {
                    return 0.01M;
                }
            }
            else
            {
                return 1M;
            }

        }

        private async Task<SpuEntity?> GetSpuEntityAsync(int id)
        {
            var Spus = _dBContext.GetDbSet<SpuEntity>();
            var Skus = _dBContext.GetDbSet<SkuEntity>();
            var SkuSafetyStocks = _dBContext.GetDbSet<SkuSafetyStockEntity>();
            var entity = await (
                 from m in Spus
                 where m.id == id
                 select new SpuEntity
                 {
                     id = m.id,
                     spu_code = m.spu_code,
                     spu_name = m.spu_name,
                     category_id = m.category_id,
                     spu_description = m.spu_description,
                     supplier_id = m.supplier_id,
                     supplier_name = m.supplier_name,
                     brand = m.brand,
                     origin = m.origin,
                     length_unit = m.length_unit,
                     volume_unit = m.volume_unit,
                     weight_unit = m.weight_unit,
                     creator = m.creator,
                     create_time = m.create_time,
                     last_update_time = m.last_update_time,
                     is_valid = m.is_valid,
                     detailList = Skus.Where(t => t.spu_id.Equals(m.id))
                                  .Select(t => new SkuEntity
                                  {
                                      Spu = m,
                                      id = t.id,
                                      spu_id = t.spu_id,
                                      sku_code = t.sku_code,
                                      sku_name = t.sku_name,
                                      bar_code = t.bar_code,
                                      weight = t.weight,
                                      lenght = t.lenght,
                                      width = t.width,
                                      height = t.height,
                                      volume = t.volume,
                                      unit = t.unit,
                                      cost = t.cost,
                                      price = t.price,
                                      create_time = t.create_time,
                                      last_update_time = t.last_update_time,
                                      detailList = (from sss in SkuSafetyStocks
                                                    where sss.sku_id.Equals(t.id)
                                                    select new SkuSafetyStockEntity
                                                    {
                                                        Sku = t,
                                                        id = sss.id,
                                                        sku_id = sss.sku_id,
                                                        safety_stock_qty = sss.safety_stock_qty,
                                                        warehouse_id = sss.warehouse_id
                                                    }).ToList()
                                  }).ToList()

                 }).FirstOrDefaultAsync();
            return entity;
        }
        /// <summary>
        /// update a record
        /// </summary>
        /// <param name="viewModel">args</param>
        /// <returns></returns>
        public async Task<(bool flag, string msg)> UpdateAsync(SpuBothViewModel viewModel)
        {
            var DbSet = _dBContext.GetDbSet<SpuEntity>();
            var entity = await DbSet.Include(d => d.detailList)
                .FirstOrDefaultAsync(t => t.id.Equals(viewModel.id));
            if (entity == null)
            {
                return (false, _stringLocalizer["not_exists_entity"]);
            }
            if (await DbSet.AsNoTracking().AnyAsync(t => !t.id.Equals(viewModel.id) && t.tenant_id.Equals(entity.tenant_id) && t.spu_code.Equals(viewModel.spu_code)))
            {
                return (false, string.Format(_stringLocalizer["exists_entity"], _stringLocalizer["spu_code"], viewModel.spu_code));
            }
            entity.spu_code = viewModel.spu_code;
            entity.spu_name = viewModel.spu_name;
            entity.category_id = viewModel.category_id;
            entity.spu_description = viewModel.spu_description;
            entity.supplier_id = viewModel.supplier_id;
            entity.supplier_name = viewModel.supplier_name;
            entity.brand = viewModel.brand;
            entity.origin = viewModel.origin;
            entity.length_unit = viewModel.length_unit;
            entity.volume_unit = viewModel.volume_unit;
            entity.weight_unit = viewModel.weight_unit;
            entity.is_valid = viewModel.is_valid;
            entity.last_update_time = DateTime.Now;
           
            
            if (viewModel.detailList.Any(t => t.id > 0))
            {
                entity.detailList.ForEach(d =>
                {
                    var vm = viewModel.detailList.Where(t => t.id > 0).FirstOrDefault(t => t.id == d.id);
                    if (vm != null)
                    {
                        d.sku_code = vm.sku_code;
                        d.sku_name = vm.sku_name;
                        d.bar_code = vm.bar_code;
                        d.image_url = vm.image_url;
                        d.weight = vm.weight;
                        d.lenght = vm.lenght;
                        d.width = vm.width;
                        d.height = vm.height;
                        d.volume = vm.volume;
                        d.unit = vm.unit;
                        d.cost = vm.cost;
                        d.price = vm.price;
                        d.last_update_time = DateTime.Now;
                    }
                });
            }
            if (viewModel.detailList.Any(t => t.id == 0))
            {
                entity.detailList.AddRange(viewModel.detailList.Where(t => t.id == 0).ToList().Adapt<List<SkuEntity>>());
            }
            if (viewModel.detailList.Any(t => t.id < 0))
            {
                var delIds = viewModel.detailList.Where(t => t.id < 0).Select(t => t.id * -1).ToList();
                entity.detailList.RemoveAll(entity => delIds.Contains(entity.id));
            }
            var qty = await _dBContext.SaveChangesAsync();
            if (qty > 0)
            {
                decimal dec = ChangeLengthUnit(entity.length_unit, entity.volume_unit);
                await _dBContext.GetDbSet<SkuEntity>().Where(t => t.spu_id.Equals(entity.id))
                    .ExecuteUpdateAsync(p => p.SetProperty(x => x.volume, x => Math.Round(x.lenght * dec * x.width * dec * x.height * dec, 3)));
                return (true, _stringLocalizer["save_success"]);
            }
            else
            {
                return (false, _stringLocalizer["save_failed"]);
            }
        }
        /// <summary>
        /// delete a record
        /// </summary>
        /// <param name="id">id</param>
        /// <returns></returns>
        public async Task<(bool flag, string msg)> DeleteAsync(int id)
        {
            var Asns = _dBContext.GetDbSet<AsnEntity>();
            if(await Asns.AsNoTracking().AnyAsync(t => t.spu_id.Equals(id)))
            {
                return (false, _stringLocalizer["delete_referenced"]);
            }
            var qty = await _dBContext.GetDbSet<SkuEntity>().Where(t => t.spu_id.Equals(id)).ExecuteDeleteAsync();
            qty += await _dBContext.GetDbSet<SpuEntity>().Where(t => t.id.Equals(id)).ExecuteDeleteAsync();
            if (qty > 0)
            {
                return (true, _stringLocalizer["delete_success"]);
            }
            else
            {
                return (false, _stringLocalizer["delete_failed"]);
            }
        }
        #endregion

        #region add or update sku_safety_stock
        /// <summary>
        /// add or update sku_safety_stock
        /// </summary>
        /// <param name="viewModel">args</param>
        /// <returns></returns>
        public async Task<(bool flag, string msg)> InsertOrUpdateSkuSafetyStockAsync(SkuSafetyStockPutViewModel viewModel)
        {
            if (viewModel.detailList.Any())
            {
                var SafetyDB = _dBContext.GetDbSet<SkuSafetyStockEntity>();
                var entities = await SafetyDB.Where(t => t.sku_id == viewModel.sku_id)
                    .ToListAsync();
                viewModel.detailList.ForEach(async t =>
                {
                    if (t.id == 0)
                    {
                        await SafetyDB.AddAsync(new SkuSafetyStockEntity { sku_id = viewModel.sku_id, safety_stock_qty = t.safety_stock_qty, warehouse_id = t.warehouse_id });
                        
                    }
                    else
                    {
                        var ent = entities.FirstOrDefault(e => e.id == Math.Abs(t.id));
                        if (ent != null)
                        {
                            if (t.id < 0)
                            {
                                SafetyDB.Remove(ent);
                            }
                            else
                            {
                                ent.warehouse_id = t.warehouse_id;
                                ent.safety_stock_qty = t.safety_stock_qty;
                            }
                        }
                    }
                });
                await _dBContext.SaveChangesAsync();
                return (true, _stringLocalizer["save_success"]);
            }
            else
            {
                return (false, _stringLocalizer["save_failed"]);
            }
        }

        #endregion
    }
}
 
