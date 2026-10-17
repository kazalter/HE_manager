#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_4.h>
#include <wrl/client.h>
#include <atomic>
#include <thread>
#include <memory>
#include <algorithm>
#include <stdexcept>
#include <mutex>
#include "include/mpv/render_d3d11.h"
using Microsoft::WRL::ComPtr;
// Published WinUI ISwapChainPanelNative ABI. No XAML/business logic in this DLL.
struct PanelNative : IUnknown { virtual HRESULT STDMETHODCALLTYPE SetSwapChain(IDXGISwapChain*) = 0; };
const IID PanelIID={0x63aad0b8,0x7c24,0x40ff,{0x85,0xa8,0x64,0x0d,0x94,0x4c,0xc3,0x25}};
static void check(HRESULT hr) { if(FAILED(hr)) throw hr; }
struct Bridge {
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> context;
    ComPtr<IDXGISwapChain1> swap;
    ComPtr<PanelNative> panel;
    mpv_render_context* render=nullptr;
    decltype(&mpv_render_context_free) freeRender=nullptr;
    decltype(&mpv_render_context_update) update=nullptr;
    decltype(&mpv_render_context_render) draw=nullptr;
    decltype(&mpv_render_context_report_swap) reportSwap=nullptr;
    decltype(&mpv_render_context_set_update_callback) setCallback=nullptr;
    HANDLE wake=CreateEventW(nullptr,FALSE,FALSE,nullptr);
    std::thread worker;
    std::atomic<bool> stopping{false};
    std::atomic<unsigned> width{1280},height{720};
    std::atomic<float> scale{1};
    std::atomic<bool> resized{false};
    std::atomic<bool> suspended{false};
    std::mutex resizeLock;
    std::atomic<int> error{0};
    std::atomic<unsigned long long> frames{0};
    std::atomic<bool> probing{false};
    std::atomic<unsigned> pixelSpread{0};
    std::atomic<unsigned long long> readbackFrame{0};
    std::atomic<unsigned> surfaceWidth{0},surfaceHeight{0};
    static void notify(void* p) { SetEvent(static_cast<Bridge*>(p)->wake); }
    ~Bridge() {
        stopping=true; SetEvent(wake);
        if(worker.joinable()) worker.join();
        if(render) { setCallback(render,nullptr,nullptr); freeRender(render); }
        if(panel) panel->SetSwapChain(nullptr); // caller destroys on XAML thread
        CloseHandle(wake);
    }
    void loop() {
        try {
            while(!stopping) {
                WaitForSingleObject(wake,50);
                if(stopping) break;
                bool force=resized.exchange(false);
                if(force) {
                    std::lock_guard<std::mutex> guard(resizeLock);
                    context->ClearState(); context->Flush();
                    check(swap->ResizeBuffers(2,width.load(),height.load(),DXGI_FORMAT_B8G8R8A8_UNORM,0));
                    ComPtr<IDXGISwapChain2> s2; check(swap.As(&s2));
                    float inv=1/scale.load(); DXGI_MATRIX_3X2_F matrix={inv,0,0,inv,0,0};
                    check(s2->SetMatrixTransform(&matrix));
                }
                auto flags=update(render);
                if(!(flags & MPV_RENDER_UPDATE_FRAME) && !force) continue;
                if(suspended) {
                    int skip=1;
                    mpv_render_param params[]={{MPV_RENDER_PARAM_SKIP_RENDERING,&skip},{MPV_RENDER_PARAM_INVALID,nullptr}};
                    int result=draw(render,params);if(result<0){error=result;break;}
                    reportSwap(render);continue;
                }
                ComPtr<ID3D11Texture2D> target;
                check(swap->GetBuffer(0,IID_PPV_ARGS(&target)));
                D3D11_TEXTURE2D_DESC targetDesc{};target->GetDesc(&targetDesc);surfaceWidth=targetDesc.Width;surfaceHeight=targetDesc.Height;
                mpv_d3d11_fbo fbo={target.Get()};
                mpv_render_param params[]={{MPV_RENDER_PARAM_D3D11_FBO,&fbo},{MPV_RENDER_PARAM_INVALID,nullptr}};
                int result=draw(render,params);
                if(result<0) {error=result;break;}
                // Optional GPU readback only for the smoke probe, never for normal playback.
                if(probing && frames.load()%30==0) {
                    D3D11_TEXTURE2D_DESC desc{};target->GetDesc(&desc);
                    desc.Usage=D3D11_USAGE_STAGING;desc.BindFlags=0;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;desc.MiscFlags=0;
                    ComPtr<ID3D11Texture2D> readback;check(device->CreateTexture2D(&desc,nullptr,&readback));
                    context->CopyResource(readback.Get(),target.Get());
                    D3D11_MAPPED_SUBRESOURCE mapped{};check(context->Map(readback.Get(),0,D3D11_MAP_READ,0,&mapped));
                    unsigned low=255,high=0;
                    for(unsigned y=0;y<desc.Height;y+=std::max(1u,desc.Height/32))
                        for(unsigned x=0;x<desc.Width;x+=std::max(1u,desc.Width/32)) {
                            auto p=static_cast<unsigned char*>(mapped.pData)+y*mapped.RowPitch+x*4;
                            for(int c=0;c<3;c++){low=std::min(low,unsigned(p[c]));high=std::max(high,unsigned(p[c]));}
                        }
                    context->Unmap(readback.Get(),0);pixelSpread=high-low;readbackFrame=frames.load()+1;
                }
                check(swap->Present(1,0)); reportSwap(render); ++frames;
            }
        } catch(HRESULT hr) {error=hr;} catch(...) {error=E_FAIL;}
    }
};
#define EXPORT extern "C" __declspec(dllexport)
EXPORT int __cdecl he_graphics_create(mpv_handle* mpv,IUnknown* panel,void** output) {
    *output=nullptr;
    try {
        auto b=std::make_unique<Bridge>();
        if(!b->wake) return HRESULT_FROM_WIN32(GetLastError());
        auto dll=GetModuleHandleW(L"libmpv-2.dll");
        if(!dll) return E_NOINTERFACE;
#define LOAD(field,name) b->field=reinterpret_cast<decltype(b->field)>(GetProcAddress(dll,name)); if(!b->field) return E_NOINTERFACE;
        LOAD(freeRender,"mpv_render_context_free") LOAD(update,"mpv_render_context_update")
        LOAD(draw,"mpv_render_context_render") LOAD(reportSwap,"mpv_render_context_report_swap")
        LOAD(setCallback,"mpv_render_context_set_update_callback")
        auto create=reinterpret_cast<decltype(&mpv_render_context_create)>(GetProcAddress(dll,"mpv_render_context_create"));
        if(!create) return E_NOINTERFACE;
        // Prefer discrete hardware on hybrid laptops; no software rasterizer fallback.
        ComPtr<IDXGIFactory1> factory; check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)));
        ComPtr<IDXGIAdapter1> selected;
        SIZE_T largest=0;
        for(UINT i=0;;i++) {
            ComPtr<IDXGIAdapter1> a; auto hr=factory->EnumAdapters1(i,&a);if(hr==DXGI_ERROR_NOT_FOUND)break;check(hr);
            DXGI_ADAPTER_DESC1 desc{}; check(a->GetDesc1(&desc));
            if(!(desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) && (!selected || desc.DedicatedVideoMemory>largest)) {selected=a;largest=desc.DedicatedVideoMemory;}
        }
        check(D3D11CreateDevice(selected.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,D3D11_CREATE_DEVICE_BGRA_SUPPORT,nullptr,0,D3D11_SDK_VERSION,&b->device,nullptr,&b->context));
        ComPtr<IDXGIFactory2> f2; check(factory.As(&f2));
        DXGI_SWAP_CHAIN_DESC1 desc{};
        desc.Width=1280;desc.Height=720;desc.Format=DXGI_FORMAT_B8G8R8A8_UNORM;
        desc.SampleDesc.Count=1;desc.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT;
        desc.BufferCount=2;desc.SwapEffect=DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL;
        desc.Scaling=DXGI_SCALING_STRETCH;desc.AlphaMode=DXGI_ALPHA_MODE_IGNORE;
        check(f2->CreateSwapChainForComposition(b->device.Get(),&desc,nullptr,&b->swap));
        mpv_d3d11_init_params init={b->device.Get()};
        int advanced=1; // independent renderer never waits on any client API thread
        mpv_render_param params[]={{MPV_RENDER_PARAM_API_TYPE,(void*)MPV_RENDER_API_TYPE_D3D11},
            {MPV_RENDER_PARAM_D3D11_INIT_PARAMS,&init},{MPV_RENDER_PARAM_ADVANCED_CONTROL,&advanced},{MPV_RENDER_PARAM_INVALID,nullptr}};
        int result=create(&b->render,mpv,params); if(result<0) return result;
        check(panel->QueryInterface(PanelIID,reinterpret_cast<void**>(b->panel.GetAddressOf())));
        check(b->panel->SetSwapChain(b->swap.Get()));
        b->setCallback(b->render,Bridge::notify,b.get());
        b->worker=std::thread([p=b.get()] {p->loop();});
        *output=b.release(); return 0;
    } catch(HRESULT hr) {return hr;} catch(...) {return E_FAIL;}
}
EXPORT void __cdecl he_graphics_resize(Bridge* b,unsigned w,unsigned h,float scale) {
    std::lock_guard<std::mutex> guard(b->resizeLock);
    b->width=w?w:1;b->height=h?h:1;b->scale=scale>0?scale:1;b->resized=true;SetEvent(b->wake);
}
EXPORT unsigned long long __cdecl he_graphics_frames(Bridge* b) {return b->frames.load();}
EXPORT int __cdecl he_graphics_error(Bridge* b) {return b->error.load();}
EXPORT void __cdecl he_graphics_destroy(Bridge* b) {delete b;}

EXPORT void __cdecl he_graphics_probe(Bridge* b) {b->probing=true;}
EXPORT unsigned __cdecl he_graphics_pixel_spread(Bridge* b) {return b->pixelSpread.load();}

EXPORT void __cdecl he_graphics_suspend(Bridge* b,bool suspended) {
    b->suspended=suspended;SetEvent(b->wake);
}
EXPORT long long __cdecl he_graphics_gpu_bytes(Bridge* b) {
    ComPtr<IDXGIDevice> dxgi; if(FAILED(b->device.As(&dxgi)))return -1;
    ComPtr<IDXGIAdapter> adapter;if(FAILED(dxgi->GetAdapter(&adapter)))return -1;
    ComPtr<IDXGIAdapter3> a3;if(FAILED(adapter.As(&a3)))return -1;
    DXGI_QUERY_VIDEO_MEMORY_INFO info{};
    if(FAILED(a3->QueryVideoMemoryInfo(0,DXGI_MEMORY_SEGMENT_GROUP_LOCAL,&info)))return -1;
    return static_cast<long long>(info.CurrentUsage);
}

EXPORT unsigned __cdecl he_graphics_width(Bridge* b) {return b->surfaceWidth.load();}
EXPORT unsigned __cdecl he_graphics_height(Bridge* b) {return b->surfaceHeight.load();}

EXPORT unsigned long long __cdecl he_graphics_readback_frame(Bridge* b) {return b->readbackFrame.load();}
