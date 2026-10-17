using System.Security.Cryptography;
using System.Text;

namespace HEManager.Core;

public sealed record ServerAddress
{
    public Uri BaseUri { get; }
    public string Key { get; }
    ServerAddress(Uri uri)
    {
        BaseUri=uri;
        Key=Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(uri.AbsoluteUri))).ToLowerInvariant();
    }
    public static ServerAddress Parse(string value)
    {
        if(!Uri.TryCreate(value.Trim(),UriKind.Absolute,out var uri) || uri.Scheme is not ("http" or "https") || string.IsNullOrEmpty(uri.Host) || uri.UserInfo.Length!=0 || uri.Query.Length!=0 || uri.Fragment.Length!=0)
            throw new ArgumentException("请输入完整的 HTTP 或 HTTPS 服务器地址，不包含账号、查询参数或片段。");
        return new(new Uri(uri.AbsoluteUri.TrimEnd('/')+"/"));
    }
    public Uri Endpoint(string path)
    {
        if(path.StartsWith('/') || Uri.TryCreate(path,UriKind.Absolute,out _))throw new ArgumentException("API path must be relative.");
        var endpoint=new Uri(BaseUri,path);
        if(!BaseUri.IsBaseOf(endpoint))throw new ArgumentException("API path escaped server base.");
        return endpoint;
    }
    public override string ToString()=>BaseUri.AbsoluteUri.TrimEnd('/');
}
