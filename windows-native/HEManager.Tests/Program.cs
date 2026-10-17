using HEManager.Core;
using HEManager.Windows;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Security.Cryptography;

static class Tests
{
    const string User="{\"id\":7,\"username\":\"fixture\",\"is_admin\":false,\"is_active\":true}";
    static void Require(bool value,string message) {if(!value)throw new Exception(message);}
    static async Task Throws<T>(Func<Task> work) where T:Exception
    {try {await work();} catch(T) {return;} throw new Exception("Expected "+typeof(T).Name);}
    static HttpResponseMessage Json(string text,HttpStatusCode code=HttpStatusCode.OK)=>new(code){Content=new StringContent(text,Encoding.UTF8,"application/json")};
    static HeApiClient Api(ServerAddress server,Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> send)=>new(server,new Handler(send));
    static async Task Main()
    {
        ServerAddress a=ServerAddress.Parse("http://one.invalid/api"),b=ServerAddress.Parse("http://two.invalid");
        Require(a==ServerAddress.Parse("http://one.invalid/api/"),"Trailing slash changed server identity");
        Require(a.Endpoint("auth/status").AbsolutePath=="/api/auth/status","API prefix lost");
        foreach(var invalid in new[]{"file:///tmp/x","https://user:pass@one.invalid","https://one.invalid?token=x"})
            await Throws<ArgumentException>(()=>Task.FromResult(ServerAddress.Parse(invalid)));
        Console.WriteLine("PASS server-address-and-prefix");
        var store=new Store();int calls=0;
        using(var session=new ConnectionSession(Api(a,async (request,ct)=>
        {
            calls++;Require(request.RequestUri==a.Endpoint("auth/login"),"Wrong login destination");
            Require(request.Headers.Authorization==null,"Login carried an old token");
            using var body=JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct));
            Require(body.RootElement.GetProperty("username").GetString()=="fixture" && body.RootElement.GetProperty("password").GetString()=="fixture password ","Login body changed");
            return Json("{\"access_token\":\"fixture-token\",\"user\":"+User+"}");
        }),store))
        {
            await session.LoginAsync(" fixture ","fixture password ");
            Require(session.User?.Id==7 && store.Read(a)=="fixture-token" && store.Read(b)==null && calls==1,"Login or server isolation failed");
        }
        Require(store.Read(a)=="fixture-token","Normal close removed remembered login");
        using(var other=new ConnectionSession(Api(b,(request,ct)=>throw new Exception("Another server reused credentials")),store))Require(!await other.RestoreAsync(),"Another server restored credentials");
        Console.WriteLine("PASS login-normal-close-and-server-isolation");
        using(var expired=new ConnectionSession(Api(a,(request,ct)=>
        {
            Require(request.Headers.Authorization?.ToString()=="Bearer fixture-token","Token not in Authorization header");
            Require(request.RequestUri!.Query=="","Token leaked to URL");
            return Task.FromResult(Json("{}",HttpStatusCode.Unauthorized));
        }),store))
        {
            await Throws<HeApiException>(()=>expired.RestoreAsync());
            Require(store.Read(a)==null && expired.User==null,"401 retained expired identity");
        }
        Console.WriteLine("PASS expired-login-clears-identity");
        var started=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using(var cancelled=new ConnectionSession(Api(a,async (request,ct)=>
        {started.SetResult();await Task.Delay(Timeout.Infinite,ct);return Json("{}");}),store))
        {
            var login=cancelled.LoginAsync("fixture","fixture");await started.Task;cancelled.Dispose();
            await Throws<OperationCanceledException>(()=>login);
            Require(store.Read(a)==null && cancelled.User==null,"Cancelled login changed identity");
        }
        var staleStarted=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var staleReply=new TaskCompletionSource<HttpResponseMessage>(TaskCreationOptions.RunContinuationsAsynchronously);
        store.Write(a,"expired-old-token");
        using(var stale=new ConnectionSession(Api(a,(request,ct)=>{staleStarted.SetResult();return staleReply.Task;}),store))
        {
            var restore=stale.RestoreAsync();await staleStarted.Task;stale.Dispose();
            store.Write(a,"new-scope-token");staleReply.SetResult(Json("{}",HttpStatusCode.Unauthorized));
            try {await restore;throw new Exception("Old request unexpectedly succeeded");}
            catch(OperationCanceledException) {}
            catch(HeApiException ex) when(ex.Status==HttpStatusCode.Unauthorized) {}
            Require(store.Read(a)=="new-scope-token","Stale 401 deleted the new scope credential");
        }
        Console.WriteLine("PASS server-switch-cancellation-and-stale-401-isolation");
        store.Write(a,"fixture-token");
        using(var offline=new ConnectionSession(Api(a,(request,ct)=>request.RequestUri!.AbsolutePath.EndsWith("auth/me")?Task.FromResult(Json(User)):throw new HttpRequestException("offline fixture")),store))
        {
            await offline.RestoreAsync();Require(!await offline.LogoutAsync(),"Offline logout claimed server confirmation");
            Require(store.Read(a)==null && offline.User==null,"Offline logout retained local identity");
        }
        using(var malformed=Api(a,(request,ct)=>Task.FromResult(Json("{}"))))await Throws<InvalidDataException>(()=>malformed.StatusAsync(default));
        Console.WriteLine("PASS offline-logout-and-malformed-response");
        if(OperatingSystem.IsWindows())
        {
            string directory=Path.Combine(Path.GetTempPath(),"he-account-test-"+Guid.NewGuid().ToString("N"));
            try
            {
                var protectedStore=new AccountStorage(directory);protectedStore.Write(a,"fixture-token-for-dpapi");
                Require(protectedStore.Read(a)=="fixture-token-for-dpapi","DPAPI round trip failed");
                Require(!Encoding.UTF8.GetString(File.ReadAllBytes(Path.Combine(directory,a.Key+".bin"))).Contains("fixture-token-for-dpapi"),"Token was stored in plaintext");
                File.Copy(Path.Combine(directory,a.Key+".bin"),Path.Combine(directory,b.Key+".bin"));
                await Throws<CryptographicException>(()=>Task.FromResult(protectedStore.Read(b)));
                protectedStore.Delete(a);Require(protectedStore.Read(a)==null,"Credential delete failed");
                Console.WriteLine("PASS current-user-DPAPI-and-server-bound-encryption");
            }
            finally {if(Directory.Exists(directory))Directory.Delete(directory,true);}
        }
    }
    sealed class Store:ICredentialStore
    {
        readonly Dictionary<string,string> values=[];
        public string? Read(ServerAddress server)=>values.GetValueOrDefault(server.Key);
        public void Write(ServerAddress server,string token)=>values[server.Key]=token;
        public void Delete(ServerAddress server)=>values.Remove(server.Key);
    }
    sealed class Handler(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken ct)=>send(request,ct);}
}
