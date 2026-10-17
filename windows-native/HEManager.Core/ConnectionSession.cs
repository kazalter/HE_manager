namespace HEManager.Core;

public interface ICredentialStore
{
    string? Read(ServerAddress server);
    void Write(ServerAddress server,string token);
    void Delete(ServerAddress server);
}

// Own every request and credential in one server scope; a server switch cancels it.
public sealed class ConnectionSession:IDisposable
{
    readonly ICredentialStore credentials;
    readonly CancellationTokenSource lifetime=new();
    readonly CancellationToken cancellation;
    readonly object stateLock=new();
    string? token;
    bool disposed;
    public HeApiClient Api { get; }
    public HeUser? User { get; private set; }
    public bool HasCredentials=>token!=null;
    public CancellationToken Cancellation=>cancellation;
    public ConnectionSession(HeApiClient api,ICredentialStore credentials) {Api=api;this.credentials=credentials;cancellation=lifetime.Token;}
    void CheckActive() {if(disposed||Cancellation.IsCancellationRequested)throw new OperationCanceledException(Cancellation);}
    public async Task<bool> RestoreAsync()
    {
        string? remembered;
        lock(stateLock) {CheckActive();remembered=credentials.Read(Api.Server);token=remembered;User=null;}
        if(remembered==null)return false;
        try
        {
            var user=await Api.MeAsync(remembered,Cancellation).ConfigureAwait(false);
            lock(stateLock) {CheckActive();User=user;}return true;
        }
        catch(HeApiException ex) when(ex.Status==System.Net.HttpStatusCode.Unauthorized)
        {
            // An old 401 must not delete credentials saved by a newer server scope.
            lock(stateLock) {if(!disposed&&!Cancellation.IsCancellationRequested)Forget();}
            throw;
        }
    }
    public async Task LoginAsync(string username,string password)
    {
        var result=await Api.LoginAsync(username,password,Cancellation).ConfigureAwait(false);
        lock(stateLock)
        {
            CheckActive();
            // Persist before publishing success; never store the password.
            credentials.Write(Api.Server,result.AccessToken);
            token=result.AccessToken;User=result.User;
        }
    }
    public async Task<bool> LogoutAsync()
    {
        string? old;
        // A failed local delete leaves the current identity visible so the user can retry.
        lock(stateLock) {CheckActive();old=token;Forget();}
        if(old==null)return true;
        try {await Api.LogoutAsync(old,Cancellation).ConfigureAwait(false);return true;}
        catch(HttpRequestException) {return false;}
        catch(OperationCanceledException) when(!Cancellation.IsCancellationRequested) {return false;}
        catch(HeApiException) {return false;}
    }
    void Forget() {credentials.Delete(Api.Server);token=null;User=null;}
    public void Dispose()
    {
        lock(stateLock) {if(disposed)return;disposed=true;token=null;User=null;}
        lifetime.Cancel();Api.Dispose();lifetime.Dispose();
    }
}
