#pragma once
#include <cstdint>
#include <memory>
#include <stdexcept>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include "include/mpv/render_d3d11.h"
using Microsoft::WRL::ComPtr;
inline void checked(HRESULT value, const char* operation = "D3D11 operation") {
    if (FAILED(value)) throw std::runtime_error(std::string(operation) + " failed: " + std::to_string(static_cast<unsigned long>(value)));
}
struct Surface {
    unsigned width, height;
    ComPtr<ID3D11Texture2D> texture;
    HANDLE handle = nullptr;
    ~Surface() { if (handle) CloseHandle(handle); }
    void* nativeHandle() const { return handle; }
};
struct Graphics {
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> context;
    ComPtr<ID3D11Query> completion;
    mpv_d3d11_init_params init{};
    void create(unsigned vendor, unsigned deviceId) {
        ComPtr<IDXGIFactory1> factory;
        checked(CreateDXGIFactory1(IID_PPV_ARGS(&factory)));
        ComPtr<IDXGIAdapter1> selected;
        for (UINT i = 0;; ++i) {
            ComPtr<IDXGIAdapter1> adapter;
            const auto result = factory->EnumAdapters1(i, &adapter);
            if (result == DXGI_ERROR_NOT_FOUND) break;
            checked(result);
            DXGI_ADAPTER_DESC1 desc{}; checked(adapter->GetDesc1(&desc));
            if (desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) continue;
            if (!selected) selected = adapter;
            if (desc.VendorId == vendor && desc.DeviceId == deviceId) { selected = adapter; break; }
        }
        if (!selected) throw std::runtime_error("No hardware D3D11 adapter");
        checked(D3D11CreateDevice(selected.Get(), D3D_DRIVER_TYPE_UNKNOWN, nullptr,
            D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0, D3D11_SDK_VERSION, &device, nullptr, &context));
        D3D11_QUERY_DESC query{D3D11_QUERY_EVENT, 0};
        checked(device->CreateQuery(&query, &completion));
        init.device = device.Get();
    }
    const char* apiType() { return MPV_RENDER_API_TYPE_D3D11; }
    mpv_render_param initParam() { return {MPV_RENDER_PARAM_D3D11_INIT_PARAMS, &init}; }
    std::unique_ptr<Surface> surface(unsigned w, unsigned h) {
        auto result = std::make_unique<Surface>(); result->width = w; result->height = h;
        D3D11_TEXTURE2D_DESC desc{};
        desc.Width = w; desc.Height = h; desc.MipLevels = 1; desc.ArraySize = 1;
        desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM; desc.SampleDesc.Count = 1;
        desc.Usage = D3D11_USAGE_DEFAULT;
        desc.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
        // Electron's BGRA import expects an NT handle without a keyed mutex.
        desc.MiscFlags = D3D11_RESOURCE_MISC_SHARED_NTHANDLE | D3D11_RESOURCE_MISC_SHARED;
        checked(device->CreateTexture2D(&desc, nullptr, &result->texture), "CreateTexture2D(shared NT)");
        ComPtr<IDXGIResource1> shared; checked(result->texture.As(&shared));
        checked(shared->CreateSharedHandle(nullptr, DXGI_SHARED_RESOURCE_READ | DXGI_SHARED_RESOURCE_WRITE,
            nullptr, &result->handle), "CreateSharedHandle");
        return result;
    }
    int draw(mpv_render_context* render, Surface& target,
             int (*renderFrame)(mpv_render_context*, mpv_render_param*)) {
        mpv_d3d11_fbo fbo{target.texture.Get()};
        mpv_render_param params[] = {{MPV_RENDER_PARAM_D3D11_FBO, &fbo}, {MPV_RENDER_PARAM_INVALID, nullptr}};
        const int result = renderFrame(render, params);
        if (result < 0) return result;
        // Complete producer writes on the native thread before the other GPU
        // device imports the handle. No pixels are read back or sent over JS IPC.
        context->End(completion.Get()); context->Flush();
        for (int i = 0; i < 1000; ++i) {
            const auto state = context->GetData(completion.Get(), nullptr, 0, 0);
            if (state == S_OK) return result;
            if (state != S_FALSE) checked(state, "producer GetData");
            Sleep(1);
        }
        throw std::runtime_error("D3D11 producer synchronization timed out");
    }
    void detach(Surface&) {}
};
#else
#define GL_SILENCE_DEPRECATION
#include <CoreFoundation/CoreFoundation.h>
#include <IOSurface/IOSurface.h>
#include <OpenGL/OpenGL.h>
#include <OpenGL/gl3.h>
#include <OpenGL/CGLIOSurface.h>
#include <dlfcn.h>
#include "include/mpv-stable/render_gl.h"
struct Surface {
    unsigned width, height;
    IOSurfaceRef buffer = nullptr;
    GLuint texture = 0, framebuffer = 0;
    ~Surface() { if (buffer) CFRelease(buffer); }
    void* nativeHandle() const { return buffer; }
};
struct Graphics {
    CGLContextObj context = nullptr;
    mpv_opengl_init_params init{};
    static void* address(void*, const char* name) { return dlsym(RTLD_DEFAULT, name); }
    void create(unsigned, unsigned) {
        CGLPixelFormatAttribute attrs[] = {kCGLPFAOpenGLProfile,
            static_cast<CGLPixelFormatAttribute>(kCGLOGLPVersion_3_2_Core),
            kCGLPFAAccelerated, kCGLPFAAllowOfflineRenderers,
            static_cast<CGLPixelFormatAttribute>(0)};
        CGLPixelFormatObj format = nullptr; GLint count = 0;
        if (CGLChoosePixelFormat(attrs, &format, &count) != kCGLNoError || !format)
            throw std::runtime_error("No accelerated OpenGL format");
        const auto result = CGLCreateContext(format, nullptr, &context);
        CGLReleasePixelFormat(format);
        if (result != kCGLNoError || CGLSetCurrentContext(context) != kCGLNoError)
            throw std::runtime_error("OpenGL context creation failed");
        init.get_proc_address = address;
    }
    ~Graphics() { if (context) { CGLSetCurrentContext(nullptr); CGLReleaseContext(context); } }
    const char* apiType() { return MPV_RENDER_API_TYPE_OPENGL; }
    mpv_render_param initParam() { return {MPV_RENDER_PARAM_OPENGL_INIT_PARAMS, &init}; }
    std::unique_ptr<Surface> surface(unsigned w, unsigned h) {
        auto result = std::make_unique<Surface>(); result->width = w; result->height = h;
        auto props = CFDictionaryCreateMutable(nullptr, 0, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
        const auto put = [&](CFStringRef key, int value) {
            auto number = CFNumberCreate(nullptr, kCFNumberIntType, &value);
            CFDictionarySetValue(props, key, number); CFRelease(number);
        };
        put(kIOSurfaceWidth, w); put(kIOSurfaceHeight, h); put(kIOSurfaceBytesPerElement, 4);
        put(kIOSurfaceBytesPerRow, w * 4); put(kIOSurfacePixelFormat, 0x42475241); // BGRA
        result->buffer = IOSurfaceCreate(props); CFRelease(props);
        if (!result->buffer) throw std::runtime_error("IOSurface allocation failed");
        glGenTextures(1, &result->texture); glBindTexture(GL_TEXTURE_RECTANGLE, result->texture);
        const auto status = CGLTexImageIOSurface2D(context, GL_TEXTURE_RECTANGLE, GL_RGBA8,
            w, h, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, result->buffer, 0);
        if (status != kCGLNoError) { detach(*result); throw std::runtime_error("IOSurface OpenGL binding failed"); }
        glGenFramebuffers(1, &result->framebuffer); glBindFramebuffer(GL_FRAMEBUFFER, result->framebuffer);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_RECTANGLE, result->texture, 0);
        if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
            detach(*result); throw std::runtime_error("IOSurface framebuffer incomplete");
        }
        return result;
    }
    int draw(mpv_render_context* render, Surface& target,
             int (*renderFrame)(mpv_render_context*, mpv_render_param*)) {
        mpv_opengl_fbo fbo{static_cast<int>(target.framebuffer), static_cast<int>(target.width), static_cast<int>(target.height), GL_RGBA8};
        // IOSurface -> VideoFrame already has top-left presentation semantics.
        // An additional OpenGL flip would invert the video and subtitle glyphs.
        int flip = 0;
        mpv_render_param params[] = {{MPV_RENDER_PARAM_OPENGL_FBO, &fbo},
            {MPV_RENDER_PARAM_FLIP_Y, &flip}, {MPV_RENDER_PARAM_INVALID, nullptr}};
        const int result = renderFrame(render, params);
        // IOSurface is immutable until all Electron consumers release this frame.
        glFinish(); return result;
    }
    void detach(Surface& target) {
        if (target.framebuffer) glDeleteFramebuffers(1, &target.framebuffer);
        if (target.texture) glDeleteTextures(1, &target.texture);
        target.framebuffer = target.texture = 0;
    }
};
#endif
