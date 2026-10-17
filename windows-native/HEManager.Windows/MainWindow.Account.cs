using HEManager.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Net;
using System.Security.Cryptography;

namespace HEManager.Windows;

public partial class MainWindow
{
    readonly AccountStorage accountStorage=new();
    ApplicationSettings settings=new();
    ConnectionSession? connection;
    bool shellReady,shellStarted,playerVisible,accountBusy,serverReady,serverHasUsers;
    readonly bool diagnosticsMode=Environment.GetCommandLineArgs().Any(a=>a is "--smoke" or "--probe");
    void InitializeShell()
    {
        settings=ApplicationSettings.Read();
        ServerAddressBox.Text=settings.Server;
        ThemeChoice.SelectedIndex=settings.Theme switch {"light"=>1,"dark"=>2,_=>0};
        ApplyTheme();shellReady=true;
        Navigation.SelectedItem=diagnosticsMode?PlayerNavigation:AccountNavigation;
        ShowView(diagnosticsMode?"player":"account");
    }
    async void ShellLoaded(object sender,RoutedEventArgs e)
    {
        if(shellStarted)return;shellStarted=true;
        if(!diagnosticsMode)await ConnectAsync(false);
    }
    void NavigationChanged(NavigationView sender,NavigationViewSelectionChangedEventArgs e)
    {
        if(!shellReady)return;
        ShowView(e.IsSettingsSelected?"settings":(e.SelectedItem as NavigationViewItem)?.Tag?.ToString()??"account");
    }
    void ShowView(string view)
    {
        bool wasPlaying=playerVisible;playerVisible=view=="player";
        AccountPage.Visibility=view=="account"?Visibility.Visible:Visibility.Collapsed;
        SettingsPage.Visibility=view=="settings"?Visibility.Visible:Visibility.Collapsed;
        Root.Visibility=playerVisible?Visibility.Visible:Visibility.Collapsed;
        if(!playerVisible && wasPlaying && player!=null)
        {
            player.Stop();
            if(bridge!=IntPtr.Zero)he_graphics_suspend(bridge,true);
        }
        else if(playerVisible && !wasPlaying)
        {
            DispatcherQueue.TryEnqueue(()=>
            {
                if(closing||!playerVisible)return;
                bool existing=player!=null;OnLoaded(this,new RoutedEventArgs());ResizeVideo();
                if(bridge!=IntPtr.Zero)he_graphics_suspend(bridge,false);
                if(existing)OpenSample(this,new RoutedEventArgs());
            });
        }
    }
    bool IsCurrentSession(ConnectionSession session)=>!closing&&ReferenceEquals(connection,session);
    void ServerAddressChanged(object sender,TextChangedEventArgs e) {if(shellReady)RefreshAccountControls();}
    bool AddressUnchanged()
    {
        try {return connection?.Api.Server==ServerAddress.Parse(ServerAddressBox.Text);}
        catch(ArgumentException) {return false;}
    }
    void RefreshAccountControls()
    {
        bool signed=connection?.User!=null;
        LoginFields.Visibility=signed?Visibility.Collapsed:Visibility.Visible;
        LogoutButton.Visibility=signed?Visibility.Visible:Visibility.Collapsed;
        LogoutButton.IsEnabled=!accountBusy;
        LoginButton.IsEnabled=!accountBusy&&serverReady&&serverHasUsers&&AddressUnchanged();
        UsernameBox.IsEnabled=PasswordInput.IsEnabled=!accountBusy;
        AccountHeading.Text=signed?"已登录":"账号登录";
        SignedInText.Text=signed?$"{connection!.User!.Username} · {(connection.User.IsAdmin?"管理员":"普通账号")}":"";
        ConnectionProgress.IsActive=accountBusy;
        ConnectionProgress.Visibility=accountBusy?Visibility.Visible:Visibility.Collapsed;
    }
    async void ConnectClicked(object sender,RoutedEventArgs e)=>await ConnectAsync(true);
    async Task ConnectAsync(bool save)
    {
        ServerAddress address;
        try {address=ServerAddress.Parse(ServerAddressBox.Text);}
        catch(ArgumentException ex) {ConnectionMessage.Text=ex.Message;return;}
        if(connection?.Api.Server!=address)UsernameBox.Text="";
        connection?.Dispose();
        var scope=new ConnectionSession(new HeApiClient(address),accountStorage);connection=scope;
        serverReady=serverHasUsers=false;accountBusy=true;PasswordInput.Password="";
        ActiveServerText.Text="当前服务器："+address;
        ConnectionMessage.Text="正在连接…";RefreshAccountControls();
        string? saveWarning=null;
        settings.Server=address.ToString();
        if(save)try {settings.Save();}catch(Exception ex) when(ex is IOException or UnauthorizedAccessException) {saveWarning="服务器地址未能保存，重开后需要重新输入。";}
        try
        {
            var status=await scope.Api.StatusAsync(scope.Cancellation);
            if(!IsCurrentSession(scope))return;
            serverReady=true;serverHasUsers=status.HasUsers;
            if(!status.HasUsers)ConnectionMessage.Text="已连接。服务器还没有账号，请先在现有管理页面设置首个账号。";
            else
            {
                bool restored=await scope.RestoreAsync();if(!IsCurrentSession(scope))return;
                ConnectionMessage.Text=restored?"已连接并恢复登录。":"已连接，请登录现有账号。";
            }
            if(saveWarning!=null)ConnectionMessage.Text+="\n"+saveWarning;
        }
        catch(Exception ex) {if(IsCurrentSession(scope))ConnectionMessage.Text=FriendlyError(ex);}
        finally {if(IsCurrentSession(scope)) {accountBusy=false;RefreshAccountControls();}}
    }
    async void LoginClicked(object sender,RoutedEventArgs e)
    {
        var scope=connection;if(scope==null||accountBusy||!serverReady||!AddressUnchanged())return;
        string username=UsernameBox.Text,password=PasswordInput.Password;
        if(string.IsNullOrWhiteSpace(username)||password.Length==0) {ConnectionMessage.Text="请输入用户名和密码。";return;}
        PasswordInput.Password="";accountBusy=true;ConnectionMessage.Text="正在登录…";RefreshAccountControls();
        try {await scope.LoginAsync(username,password);if(IsCurrentSession(scope))ConnectionMessage.Text="登录成功。";}
        catch(Exception ex) {if(IsCurrentSession(scope))ConnectionMessage.Text=ex is HeApiException {Status:HttpStatusCode.Unauthorized}?"用户名或密码错误。":FriendlyError(ex);}
        finally {if(IsCurrentSession(scope)) {accountBusy=false;RefreshAccountControls();}}
    }
    async void LogoutClicked(object sender,RoutedEventArgs e)
    {
        var scope=connection;if(scope==null||accountBusy)return;
        accountBusy=true;PasswordInput.Password="";RefreshAccountControls();
        try
        {
            bool confirmed=await scope.LogoutAsync();
            if(IsCurrentSession(scope))ConnectionMessage.Text=confirmed?"已退出账号。":"已退出本机账号；网络不可用，未确认服务器注销。";
        }
        catch(Exception ex) {if(IsCurrentSession(scope))ConnectionMessage.Text=FriendlyError(ex);}
        finally {if(IsCurrentSession(scope)) {accountBusy=false;RefreshAccountControls();}}
    }
    void ThemeChanged(object sender,SelectionChangedEventArgs e)
    {
        if(!shellReady)return;
        settings.Theme=(ThemeChoice.SelectedItem as ComboBoxItem)?.Tag?.ToString()??"system";ApplyTheme();
        try {settings.Save();SettingsMessage.Text="";}
        catch(Exception ex) when(ex is IOException or UnauthorizedAccessException) {SettingsMessage.Text="外观已应用，但设置未能保存。";}
    }
    void ApplyTheme()=>ShellRoot.RequestedTheme=settings.Theme switch {"light"=>ElementTheme.Light,"dark"=>ElementTheme.Dark,_=>ElementTheme.Default};
    static string FriendlyError(Exception ex)=>ex switch
    {
        HeApiException=>ex.Message,
        OperationCanceledException=>"连接超时，请检查网络后重试。",
        HttpRequestException=>"无法连接服务器，请检查地址、网络或服务器是否运行。",
        InvalidDataException=>ex.Message,
        CryptographicException=>"保存的登录信息无法解锁，请重新登录。",
        IOException or UnauthorizedAccessException=>"无法读取或保存本机登录信息，请检查磁盘空间和目录权限。",
        _=>"操作未完成，请重试。"
    };
    void CloseConnection() {PasswordInput.Password="";connection?.Dispose();connection=null;}
}
