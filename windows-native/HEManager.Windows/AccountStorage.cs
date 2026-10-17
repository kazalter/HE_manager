using HEManager.Core;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace HEManager.Windows;

internal static class NativePaths
{
    // A child test process can use an isolated profile without touching the user's account.
    public static string Root {get;}=Path.GetFullPath(Environment.GetEnvironmentVariable("HE_MANAGER_DATA_DIRECTORY") is {Length:>0} custom?custom:Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"HEManager"));
}

internal sealed class AccountStorage:ICredentialStore
{
    readonly string root;
    public AccountStorage(string? directory=null)=>root=directory??Path.Combine(NativePaths.Root,"accounts");
    string Filename(ServerAddress server)=>Path.Combine(root,server.Key+".bin");
    public string? Read(ServerAddress server)
    {
        string path=Filename(server);if(!File.Exists(path))return null;
        byte[] encrypted=File.ReadAllBytes(path),plain=Protect(encrypted,server,false);
        try {return Encoding.UTF8.GetString(plain);}
        finally {CryptographicOperations.ZeroMemory(plain);}
    }
    public void Write(ServerAddress server,string token)
    {
        Directory.CreateDirectory(root);
        byte[] plain=Encoding.UTF8.GetBytes(token);
        try
        {
            byte[] encrypted=Protect(plain,server,true);
            string path=Filename(server),temporary=path+"."+Guid.NewGuid().ToString("N")+".tmp";
            try {File.WriteAllBytes(temporary,encrypted);File.Move(temporary,path,true);}
            finally {if(File.Exists(temporary))File.Delete(temporary);}
        }
        finally {CryptographicOperations.ZeroMemory(plain);}
    }
    public void Delete(ServerAddress server)=>File.Delete(Filename(server));
    [StructLayout(LayoutKind.Sequential)] struct Blob {public int Length;public IntPtr Data;}
    static byte[] Protect(byte[] input,ServerAddress server,bool encrypt)
    {
        // Current-user DPAPI, with server-bound entropy. No password or plaintext token on disk.
        byte[] entropy=SHA256.HashData(Encoding.UTF8.GetBytes(server.BaseUri.AbsoluteUri));
        var source=new Blob {Length=input.Length,Data=Marshal.AllocHGlobal(input.Length)};
        var salt=new Blob {Length=entropy.Length,Data=Marshal.AllocHGlobal(entropy.Length)};
        Blob output=default;
        try
        {
            Marshal.Copy(input,0,source.Data,input.Length);Marshal.Copy(entropy,0,salt.Data,entropy.Length);
            bool ok=encrypt?CryptProtectData(ref source,null,ref salt,IntPtr.Zero,IntPtr.Zero,1,out output):CryptUnprotectData(ref source,IntPtr.Zero,ref salt,IntPtr.Zero,IntPtr.Zero,1,out output);
            if(!ok)throw new CryptographicException(Marshal.GetLastWin32Error());
            byte[] result=new byte[output.Length];Marshal.Copy(output.Data,result,0,result.Length);return result;
        }
        finally
        {
            if(output.Data!=IntPtr.Zero) {Marshal.Copy(new byte[output.Length],0,output.Data,output.Length);LocalFree(output.Data);}
            if(source.Data!=IntPtr.Zero) {Marshal.Copy(new byte[input.Length],0,source.Data,input.Length);Marshal.FreeHGlobal(source.Data);}
            Marshal.FreeHGlobal(salt.Data);
        }
    }
    [DllImport("crypt32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CryptProtectData(ref Blob input,string? description,ref Blob entropy,IntPtr reserved,IntPtr prompt,uint flags,out Blob output);
    [DllImport("crypt32.dll",SetLastError=true)] static extern bool CryptUnprotectData(ref Blob input,IntPtr description,ref Blob entropy,IntPtr reserved,IntPtr prompt,uint flags,out Blob output);
    [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr memory);
}

internal sealed class ApplicationSettings
{
    public string Server {get;set;}="http://192.168.0.101:8011";
    public string Theme {get;set;}="system";
    static string Filename=>Path.Combine(NativePaths.Root,"settings.json");
    public static ApplicationSettings Read()
    {
        if(!File.Exists(Filename))return new();
        try {var value=JsonSerializer.Deserialize<ApplicationSettings>(File.ReadAllText(Filename))??new();if(string.IsNullOrWhiteSpace(value.Server))value.Server=new ApplicationSettings().Server;return value;}
        catch(Exception ex) when(ex is JsonException or IOException or UnauthorizedAccessException) {return new();}
    }
    public void Save()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Filename)!);
        string temporary=Filename+".tmp";
        File.WriteAllText(temporary,JsonSerializer.Serialize(this));File.Move(temporary,Filename,true);
    }
}
