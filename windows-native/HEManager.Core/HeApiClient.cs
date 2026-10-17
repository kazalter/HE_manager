using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace HEManager.Core;

public sealed record AuthStatus([property:JsonPropertyName("has_users"),JsonRequired] bool HasUsers);
public sealed record HeUser(int Id,string Username,[property:JsonPropertyName("is_admin")] bool IsAdmin,[property:JsonPropertyName("is_active")] bool IsActive);
public sealed record AuthToken([property:JsonPropertyName("access_token")] string AccessToken,HeUser User);
public sealed class HeApiException(HttpStatusCode status):Exception(MessageFor(status))
{
    public HttpStatusCode Status { get; }=status;
    static string MessageFor(HttpStatusCode status)=>status switch
    {
        HttpStatusCode.Unauthorized=>"账号信息无效或登录已过期，请重新登录。",
        HttpStatusCode.Forbidden=>"当前账号没有访问权限。",
        HttpStatusCode.TooManyRequests=>"请求过于频繁，请稍后重试。",
        _ when (int)status>=500=>"服务器暂时不可用，请稍后重试。",
        _=>"服务器返回了未预期的响应（"+(int)status+"）。"
    };
}

public sealed class HeApiClient:IDisposable
{
    readonly HttpClient http;
    static readonly JsonSerializerOptions Json=new(JsonSerializerDefaults.Web);
    public ServerAddress Server { get; }
    public HeApiClient(ServerAddress server,HttpMessageHandler? handler=null)
    {
        Server=server;
        http=new(handler??new HttpClientHandler {AllowAutoRedirect=false,UseCookies=false}) {Timeout=TimeSpan.FromSeconds(15)};
    }
    public Task<AuthStatus> StatusAsync(CancellationToken ct)=>ReadAsync<AuthStatus>(HttpMethod.Get,"auth/status",null,null,ct);
    public async Task<AuthToken> LoginAsync(string username,string password,CancellationToken ct)
    {
        var result=await ReadAsync<AuthToken>(HttpMethod.Post,"auth/login",new {username=username.Trim(),password},null,ct).ConfigureAwait(false);
        if(string.IsNullOrWhiteSpace(result.AccessToken)||!ValidUser(result.User))throw new InvalidDataException("服务器返回的登录信息不完整。");
        return result;
    }
    static bool ValidUser(HeUser? user)=>user is {Id:>0,IsActive:true} && !string.IsNullOrWhiteSpace(user.Username);
    public async Task<HeUser> MeAsync(string token,CancellationToken ct)
    {
        var user=await ReadAsync<HeUser>(HttpMethod.Get,"auth/me",null,token,ct).ConfigureAwait(false);
        if(!ValidUser(user))throw new InvalidDataException("服务器返回的账号信息不完整。");
        return user;
    }
    public async Task LogoutAsync(string token,CancellationToken ct)
    {
        using var request=Create(HttpMethod.Post,"auth/logout",null,token);
        using var response=await http.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,ct).ConfigureAwait(false);
        // An already expired token is effectively signed out.
        if(response.StatusCode!=HttpStatusCode.Unauthorized && !response.IsSuccessStatusCode)throw new HeApiException(response.StatusCode);
    }
    HttpRequestMessage Create(HttpMethod method,string path,object? body,string? token)
    {
        var request=new HttpRequestMessage(method,Server.Endpoint(path));
        request.Headers.Accept.Add(new("application/json"));
        if(token!=null)request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",token);
        if(body!=null)request.Content=JsonContent.Create(body,options:Json);
        return request;
    }
    async Task<T> ReadAsync<T>(HttpMethod method,string path,object? body,string? token,CancellationToken ct)
    {
        using var request=Create(method,path,body,token);
        using var response=await http.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,ct).ConfigureAwait(false);
        if(!response.IsSuccessStatusCode)throw new HeApiException(response.StatusCode);
        using var readTimeout=CancellationTokenSource.CreateLinkedTokenSource(ct);
        readTimeout.CancelAfter(TimeSpan.FromSeconds(15));
        await using var stream=await response.Content.ReadAsStreamAsync(readTimeout.Token).ConfigureAwait(false);
        using var output=new MemoryStream();
        byte[] buffer=new byte[8192];int read;
        while((read=await stream.ReadAsync(buffer,readTimeout.Token).ConfigureAwait(false))!=0)
        {
            if(output.Length+read>1024*1024)throw new InvalidDataException("服务器响应过大。");
            output.Write(buffer,0,read);
        }
        try {return JsonSerializer.Deserialize<T>(output.GetBuffer().AsSpan(0,(int)output.Length),Json)??throw new JsonException();}
        catch(JsonException) {throw new InvalidDataException("服务器响应格式无效，请检查地址是否指向 HE Manager 服务。");}
    }
    public void Dispose()=>http.Dispose();
}
