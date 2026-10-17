// Small Node-API adapter. Playback/control and rendering stay on native threads;
// JS only transfers platform handles and returns leases after Electron is done.
#include <node_api.h>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
#ifdef _WIN32
#include "include/mpv/client.h"
#else
#include "include/mpv-stable/client.h"
#endif
#include "surface.h"
using namespace std::chrono_literals;

struct Api {
#ifdef _WIN32
    HMODULE library = nullptr;
#else
    void* library = nullptr;
#endif
#define API(name) decltype(&mpv_##name) name = nullptr;
    API(create) API(initialize) API(terminate_destroy) API(set_option_string)
    API(command_async) API(set_property_async) API(observe_property) API(wait_event)
    API(get_property) API(get_property_string) API(free) API(free_node_contents) API(client_api_version)
    API(render_context_create) API(render_context_free) API(render_context_update)
    API(render_context_render) API(render_context_report_swap) API(render_context_set_update_callback)
#undef API
    void load(const std::string& file) {
#ifdef _WIN32
        const int length = MultiByteToWideChar(CP_UTF8, 0, file.c_str(), -1, nullptr, 0);
        std::wstring wide(length, L'\0'); MultiByteToWideChar(CP_UTF8, 0, file.c_str(), -1, wide.data(), length);
        library = LoadLibraryExW(wide.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
        const auto symbol = [&](const char* name) { return reinterpret_cast<void*>(GetProcAddress(library, name)); };
#else
        library = dlopen(file.c_str(), RTLD_NOW | RTLD_LOCAL);
        const auto symbol = [&](const char* name) { return dlsym(library, name); };
#endif
        if (!library) throw std::runtime_error("libmpv load failed");
#define LOAD(name) name = reinterpret_cast<decltype(name)>(symbol("mpv_" #name)); if (!name) throw std::runtime_error("libmpv API export missing: " #name);
        LOAD(create) LOAD(initialize) LOAD(terminate_destroy) LOAD(set_option_string)
        LOAD(command_async) LOAD(set_property_async) LOAD(observe_property) LOAD(wait_event)
        LOAD(get_property) LOAD(get_property_string) LOAD(free) LOAD(free_node_contents) LOAD(client_api_version)
        LOAD(render_context_create) LOAD(render_context_free) LOAD(render_context_update)
        LOAD(render_context_render) LOAD(render_context_report_swap) LOAD(render_context_set_update_callback)
#undef LOAD
    }
    ~Api() {
        if (!library) return;
#ifdef _WIN32
        FreeLibrary(library);
#else
        dlclose(library);
#endif
    }
};

enum class Ownership { Free, Rendering, Ready, Leased };
struct Slot {
    Ownership owner = Ownership::Free;
    std::unique_ptr<Surface> surface;
    uint64_t frame = 0;
};
struct Track {
    int64_t id = 0;
    std::string type, title, language;
    bool selected = false;
};
struct Snapshot {
    bool ready = false, stopped = false, paused = false, ended = false, buffering = false;
    double position = 0, duration = 0;
    int64_t dropped = 0;
    std::string error, hwdec, version, passes, aid, sid;
    double speed = 1;
    std::vector<Track> tracks;
};
struct Command { bool shaders = false; std::vector<std::string> values; };
struct Session {
    std::string library, source;
    std::vector<std::string> headers, initialShaders;
    unsigned vendor = 0, deviceId = 0;
    std::atomic<unsigned> width{640}, height{360};
    std::atomic<bool> stop{false}, wake{true}, resized{false}, retryRender{false};
    std::atomic<uint64_t> frames{0}, acquired{0}, released{0}, loads{0};
    std::atomic<unsigned long> apiVersion{0};
    std::mutex mutex, commandMutex, wakeMutex;
    std::condition_variable wakeSignal;
    Snapshot snapshot;
    std::deque<Command> commands;
    std::array<Slot, 2> slots;
    std::thread control;
    void notify() { wake = true; wakeSignal.notify_all(); }
    void shutdown() { stop = true; notify(); }
    void error(const std::string& message) { std::lock_guard<std::mutex> guard(mutex); if (snapshot.error.empty()) snapshot.error = message; }
    void enqueue(Command command) {
        std::lock_guard<std::mutex> guard(commandMutex);
        if (commands.size() >= 32) throw std::runtime_error("Native command queue full");
        commands.push_back(std::move(command));
    }
    static void updated(void* value) { static_cast<Session*>(value)->notify(); }
    static void strings(const mpv_node& node, std::string& output, unsigned depth = 0) {
        if (depth > 12 || output.size() > 32000) return;
        if (node.format == MPV_FORMAT_STRING && node.u.string) { output += node.u.string; output += '\n'; }
        if ((node.format == MPV_FORMAT_NODE_ARRAY || node.format == MPV_FORMAT_NODE_MAP) && node.u.list) {
            for (int i = 0; i < node.u.list->num && i < 256; ++i) strings(node.u.list->values[i], output, depth + 1);
        }
    }
    static std::vector<Track> tracks(const mpv_node& node) {
        std::vector<Track> output;
        if (node.format != MPV_FORMAT_NODE_ARRAY || !node.u.list) return output;
        for (int i = 0; i < node.u.list->num && i < 128; ++i) {
            const auto& item = node.u.list->values[i];
            if (item.format != MPV_FORMAT_NODE_MAP || !item.u.list) continue;
            Track track;
            for (int k = 0; k < item.u.list->num; ++k) {
                const std::string key = item.u.list->keys[k]; const auto& value = item.u.list->values[k];
                if (key == "id" && value.format == MPV_FORMAT_INT64) track.id = value.u.int64;
                if (key == "selected" && value.format == MPV_FORMAT_FLAG) track.selected = value.u.flag;
                if (value.format == MPV_FORMAT_STRING && value.u.string) {
                    if (key == "type") track.type = value.u.string;
                    if (key == "title") track.title = value.u.string;
                    if (key == "lang") track.language = value.u.string;
                }
            }
            if (track.type == "audio" || track.type == "sub") output.push_back(std::move(track));
        }
        return output;
    }
    void setList(Api& api, mpv_handle* core, const char* property, std::vector<std::string>& values) {
        std::vector<mpv_node> items(values.size());
        for (size_t i = 0; i < values.size(); ++i) { items[i].format = MPV_FORMAT_STRING; items[i].u.string = values[i].data(); }
        mpv_node_list list{static_cast<int>(items.size()), items.data(), nullptr};
        mpv_node node{}; node.format = MPV_FORMAT_NODE_ARRAY; node.u.list = &list;
        if (api.set_property_async(core, 0, property, MPV_FORMAT_NODE, &node) < 0)
            throw std::runtime_error("mpv list property rejected");
    }
    void command(Api& api, mpv_handle* core, std::vector<std::string>& values) {
        std::vector<const char*> args; for (const auto& value : values) args.push_back(value.c_str()); args.push_back(nullptr);
        if (api.command_async(core, 0, args.data()) < 0) throw std::runtime_error("mpv asynchronous command rejected");
        if (!values.empty() && values[0] == "loadfile") ++loads;
    }
    void render(Api& api, mpv_handle* core, std::atomic<bool>& initialized) {
        mpv_render_context* render = nullptr;
        Graphics graphics;
        try {
            graphics.create(vendor, deviceId);
            int advanced = 1;
            mpv_render_param params[] = {{MPV_RENDER_PARAM_API_TYPE, const_cast<char*>(graphics.apiType())},
                graphics.initParam(), {MPV_RENDER_PARAM_ADVANCED_CONTROL, &advanced}, {MPV_RENDER_PARAM_INVALID, nullptr}};
            const int result = api.render_context_create(&render, core, params);
            if (result < 0) throw std::runtime_error("mpv render context rejected: " + std::to_string(result));
            api.render_context_set_update_callback(render, updated, this);
            { std::lock_guard<std::mutex> guard(mutex); snapshot.ready = true; }
            initialized = true; notify();
            while (!stop) {
                {
                    std::unique_lock<std::mutex> lock(wakeMutex);
                    wakeSignal.wait_for(lock, 20ms, [&] { return stop || wake.load() || resized.load(); });
                }
                if (stop) break;
                wake = false;
                const bool force = resized.exchange(false);
                const auto flags = api.render_context_update(render);
                if (!(flags & MPV_RENDER_UPDATE_FRAME) && !force) continue;
                Slot* selected = nullptr;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    // A completed frame must remain available until acquire().
                    // Repainting Ready slots can starve the JS polling consumer
                    // when rendering finishes and immediately starts again.
                    for (auto& slot : slots) if (slot.owner == Ownership::Free) { selected = &slot; slot.owner = Ownership::Rendering; break; }
                    if (!selected) retryRender = true;
                }
                if (!selected) {
                    int skip = 1;
                    mpv_render_param skipParams[] = {{MPV_RENDER_PARAM_SKIP_RENDERING, &skip}, {MPV_RENDER_PARAM_INVALID, nullptr}};
                    api.render_context_render(render, skipParams);
                    api.render_context_report_swap(render);
                    continue;
                }
                const auto w = width.load(), h = height.load();
                std::unique_ptr<Surface> retired;
                Surface* target = nullptr;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    if (selected->surface && (selected->surface->width != w || selected->surface->height != h))
                        retired = std::move(selected->surface);
                    target = selected->surface.get();
                }
                if (!target) {
                    if (retired) graphics.detach(*retired);
                    auto created = graphics.surface(w, h);
                    target = created.get();
                    std::lock_guard<std::mutex> guard(mutex);
                    selected->surface = std::move(created);
                }
                const int drawn = graphics.draw(render, *target, api.render_context_render);
                if (drawn < 0) throw std::runtime_error("mpv frame render failed: " + std::to_string(drawn));
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    selected->frame = ++frames; selected->owner = Ownership::Ready;
                }
                api.render_context_report_swap(render);
            }
        } catch (const std::exception& failure) { error(failure.what()); stop = true; }
        initialized = true; notify();
        if (render) { api.render_context_set_update_callback(render, nullptr, nullptr); api.render_context_free(render); }
        // GL objects are detached on the rendering thread. IOSurface/NT handles
        // remain owned by their slots until all outstanding Electron leases end.
        for (auto& slot : slots) if (slot.surface) graphics.detach(*slot.surface);
        { std::lock_guard<std::mutex> guard(mutex); for (auto& slot : slots) if (slot.owner != Ownership::Leased) slot.owner = Ownership::Free; }
    }
    void run() {
        Api api; mpv_handle* core = nullptr; std::thread rendering; std::atomic<bool> initialized{false};
        try {
            api.load(library); apiVersion = api.client_api_version();
#ifdef _WIN32
            if (apiVersion < ((2UL << 16) | 6)) throw std::runtime_error("D3D11 needs libmpv API 2.6");
#else
            if (apiVersion < ((2UL << 16) | 5)) throw std::runtime_error("The OpenGL bridge is locked to libmpv API 2.5 or later");
#endif
            core = api.create(); if (!core) throw std::runtime_error("mpv create failed");
            const auto option = [&](const char* key, const char* value) {
                if (api.set_option_string(core, key, value) < 0) throw std::runtime_error(std::string("mpv option rejected: ") + key);
            };
            option("config", "no"); option("terminal", "no"); option("msg-level", "all=no");
            option("load-scripts", "no"); option("ytdl", "no"); option("vo", "libmpv");
            option("idle", "yes"); option("keep-open", "yes"); option("volume", "0");
#ifdef _WIN32
            option("hwdec", "d3d11va");
#else
            option("hwdec", "videotoolbox-copy");
#endif
            const int result = api.initialize(core);
            if (result < 0) throw std::runtime_error("mpv initialize failed: " + std::to_string(result));
            if (char* version = api.get_property_string(core, "mpv-version")) {
                { std::lock_guard<std::mutex> guard(mutex); snapshot.version = version; } api.free(version);
            }
            rendering = std::thread([&] { render(api, core, initialized); });
            for (int i = 0; !initialized && !stop && i < 1500; ++i) std::this_thread::sleep_for(10ms);
            if (!initialized || stop) throw std::runtime_error("Native renderer failed to start");
            api.observe_property(core, 1, "time-pos", MPV_FORMAT_DOUBLE);
            api.observe_property(core, 2, "duration", MPV_FORMAT_DOUBLE);
            api.observe_property(core, 3, "pause", MPV_FORMAT_FLAG);
            api.observe_property(core, 4, "eof-reached", MPV_FORMAT_FLAG);
            api.observe_property(core, 5, "hwdec-current", MPV_FORMAT_STRING);
            api.observe_property(core, 6, "frame-drop-count", MPV_FORMAT_INT64);
            api.observe_property(core, 7, "aid", MPV_FORMAT_STRING);
            api.observe_property(core, 8, "sid", MPV_FORMAT_STRING);
            api.observe_property(core, 9, "speed", MPV_FORMAT_DOUBLE);
            api.observe_property(core, 10, "paused-for-cache", MPV_FORMAT_FLAG);
            setList(api, core, "http-header-fields", headers);
            setList(api, core, "glsl-shaders", initialShaders);
            std::vector<std::string> load{"loadfile", source}; command(api, core, load);
            auto passesAt = std::chrono::steady_clock::now();
            while (!stop) {
                std::deque<Command> pending;
                { std::lock_guard<std::mutex> guard(commandMutex); pending.swap(commands); }
                for (auto& task : pending) {
                    if (task.shaders) setList(api, core, "glsl-shaders", task.values);
                    else command(api, core, task.values);
                }
                const auto* event = api.wait_event(core, 0.02);
                if ((event->event_id == MPV_EVENT_COMMAND_REPLY || event->event_id == MPV_EVENT_SET_PROPERTY_REPLY) && event->error < 0)
                    error("mpv asynchronous operation failed: " + std::to_string(event->error));
                if (event->event_id == MPV_EVENT_PROPERTY_CHANGE) {
                    const auto* prop = static_cast<mpv_event_property*>(event->data);
                    if (prop && prop->data) {
                        std::lock_guard<std::mutex> guard(mutex);
                        if (event->reply_userdata == 1 && prop->format == MPV_FORMAT_DOUBLE) snapshot.position = *static_cast<double*>(prop->data);
                        if (event->reply_userdata == 2 && prop->format == MPV_FORMAT_DOUBLE) snapshot.duration = *static_cast<double*>(prop->data);
                        if (event->reply_userdata == 3 && prop->format == MPV_FORMAT_FLAG) snapshot.paused = *static_cast<int*>(prop->data);
                        if (event->reply_userdata == 4 && prop->format == MPV_FORMAT_FLAG) snapshot.ended = *static_cast<int*>(prop->data);
                        if (event->reply_userdata == 5 && prop->format == MPV_FORMAT_STRING) snapshot.hwdec = *static_cast<char**>(prop->data);
                        if (event->reply_userdata == 6 && prop->format == MPV_FORMAT_INT64) snapshot.dropped = *static_cast<int64_t*>(prop->data);
                        if (event->reply_userdata == 7 && prop->format == MPV_FORMAT_STRING) snapshot.aid = *static_cast<char**>(prop->data);
                        if (event->reply_userdata == 8 && prop->format == MPV_FORMAT_STRING) snapshot.sid = *static_cast<char**>(prop->data);
                        if (event->reply_userdata == 9 && prop->format == MPV_FORMAT_DOUBLE) snapshot.speed = *static_cast<double*>(prop->data);
                        if (event->reply_userdata == 10 && prop->format == MPV_FORMAT_FLAG) snapshot.buffering = *static_cast<int*>(prop->data);
                    }
                }
                if (event->event_id == MPV_EVENT_END_FILE && static_cast<mpv_event_end_file*>(event->data)->reason == MPV_END_FILE_REASON_ERROR)
                    error("mpv could not read the source");
                if (std::chrono::steady_clock::now() - passesAt > 500ms) {
                    mpv_node node{};
                    if (api.get_property(core, "vo-passes", MPV_FORMAT_NODE, &node) >= 0) {
                        std::string text; strings(node, text); api.free_node_contents(&node);
                        std::lock_guard<std::mutex> guard(mutex); snapshot.passes = std::move(text);
                    }
                    mpv_node trackNode{};
                    if (api.get_property(core, "track-list", MPV_FORMAT_NODE, &trackNode) >= 0) {
                        auto values = tracks(trackNode); api.free_node_contents(&trackNode);
                        std::lock_guard<std::mutex> guard(mutex); snapshot.tracks = std::move(values);
                    }
                    passesAt = std::chrono::steady_clock::now();
                }
            }
        } catch (const std::exception& failure) { error(failure.what()); }
        shutdown();
        if (rendering.joinable()) rendering.join();
        if (core) api.terminate_destroy(core);
        // Explicit close releases surfaces without waiting for JS GC. Never
        // destroy a leased texture: Electron's allReferencesReleased callback
        // returns it, and this native thread performs the potentially heavy free.
        while (true) {
            std::vector<std::unique_ptr<Surface>> retired;
            bool leased = false;
            {
                std::lock_guard<std::mutex> guard(mutex);
                for (auto& slot : slots) {
                    if (slot.owner == Ownership::Leased) leased = true;
                    else if (slot.surface) retired.push_back(std::move(slot.surface));
                }
            }
            retired.clear();
            if (!leased) break;
            std::unique_lock<std::mutex> lock(wakeMutex); wakeSignal.wait_for(lock, 50ms);
        }
        { std::lock_guard<std::mutex> guard(mutex); snapshot.stopped = true; snapshot.ready = false; }
    }
};

static void napiChecked(napi_status value) { if (value != napi_ok) throw std::runtime_error("Invalid native bridge argument"); }
static std::string text(napi_env env, napi_value value) {
    size_t size; napiChecked(napi_get_value_string_utf8(env, value, nullptr, 0, &size));
    if (size > 32768) throw std::runtime_error("Native bridge string too long");
    std::string result(size, '\0'); napiChecked(napi_get_value_string_utf8(env, value, result.data(), size + 1, &size)); return result;
}
static napi_value field(napi_env env, napi_value object, const char* name) { napi_value value; napiChecked(napi_get_named_property(env, object, name, &value)); return value; }
static std::vector<std::string> list(napi_env env, napi_value value) {
    uint32_t length; napiChecked(napi_get_array_length(env, value, &length));
    if (length > 64) throw std::runtime_error("Native bridge list too long");
    std::vector<std::string> values; for (uint32_t i = 0; i < length; ++i) { napi_value item; napiChecked(napi_get_element(env, value, i, &item)); values.push_back(text(env, item)); } return values;
}
static Session* session(napi_env env, napi_value value) { void* output; napiChecked(napi_get_value_external(env, value, &output)); if (!output) throw std::runtime_error("No native session"); return static_cast<Session*>(output); }
static napi_value undefined(napi_env env) { napi_value value; napi_get_undefined(env, &value); return value; }
static void put(napi_env env, napi_value object, const char* name, const std::string& value) { napi_value result; napi_create_string_utf8(env, value.c_str(), value.size(), &result); napi_set_named_property(env, object, name, result); }
static void put(napi_env env, napi_value object, const char* name, double value) { napi_value result; napi_create_double(env, value, &result); napi_set_named_property(env, object, name, result); }
static void put(napi_env env, napi_value object, const char* name, bool value) { napi_value result; napi_get_boolean(env, value, &result); napi_set_named_property(env, object, name, result); }
#define BEGIN(size) try { size_t argc = size; napi_value argv[size]; napiChecked(napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr)); if (argc < size) throw std::runtime_error("Missing native argument");
#define END } catch (const std::exception& failure) { napi_throw_error(env, nullptr, failure.what()); return nullptr; }
static napi_value create(napi_env env, napi_callback_info info) {
    BEGIN(1)
    auto result = std::make_unique<Session>();
    result->library = text(env, field(env, argv[0], "library")); result->source = text(env, field(env, argv[0], "source"));
    result->headers = list(env, field(env, argv[0], "headers")); result->initialShaders = list(env, field(env, argv[0], "shaders"));
    napi_get_value_uint32(env, field(env, argv[0], "vendorId"), &result->vendor);
    napi_get_value_uint32(env, field(env, argv[0], "deviceId"), &result->deviceId);
    napi_value external;
    napiChecked(napi_create_external(env, result.get(), [](napi_env, void* pointer, void*) {
        auto* target = static_cast<Session*>(pointer); target->shutdown();
        std::thread([target] { if (target->control.joinable()) target->control.join(); delete target; }).detach();
    }, nullptr, &external));
    result->control = std::thread([target = result.get()] { target->run(); }); result.release(); return external;
    END
}
static napi_value state(napi_env env, napi_callback_info info) {
    BEGIN(1)
    auto* target = session(env, argv[0]); std::lock_guard<std::mutex> guard(target->mutex);
    napi_value output; napi_create_object(env, &output); auto& s = target->snapshot;
    put(env, output, "ready", s.ready); put(env, output, "stopped", s.stopped); put(env, output, "paused", s.paused); put(env, output, "ended", s.ended);
    put(env, output, "position", s.position); put(env, output, "duration", s.duration); put(env, output, "error", s.error);
    put(env, output, "hwdec", s.hwdec); put(env, output, "version", s.version); put(env, output, "passes", s.passes);
    put(env, output, "aid", s.aid); put(env, output, "sid", s.sid); put(env, output, "speed", s.speed);
    put(env, output, "buffering", s.buffering);
    napi_value trackList; napi_create_array_with_length(env, s.tracks.size(), &trackList);
    for (size_t i = 0; i < s.tracks.size(); ++i) {
        const auto& track = s.tracks[i]; napi_value item; napi_create_object(env, &item);
        put(env, item, "id", static_cast<double>(track.id)); put(env, item, "type", track.type);
        put(env, item, "title", track.title); put(env, item, "language", track.language); put(env, item, "selected", track.selected);
        napi_set_element(env, trackList, i, item);
    }
    napi_set_named_property(env, output, "tracks", trackList);
    put(env, output, "apiVersion", static_cast<double>(target->apiVersion));
    put(env, output, "renderedFrames", static_cast<double>(target->frames)); put(env, output, "acquiredFrames", static_cast<double>(target->acquired));
    put(env, output, "releasedFrames", static_cast<double>(target->released)); put(env, output, "sourceLoads", static_cast<double>(target->loads));
    put(env, output, "droppedFrames", static_cast<double>(s.dropped));
    int leases = 0; for (auto& slot : target->slots) if (slot.owner == Ownership::Leased) ++leases;
    int surfaces = 0; for (auto& slot : target->slots) if (slot.surface) ++surfaces;
    int readyFrames = 0; for (auto& slot : target->slots) if (slot.owner == Ownership::Ready) ++readyFrames;
    put(env, output, "readyFrames", static_cast<double>(readyFrames));
    put(env, output, "leases", static_cast<double>(leases)); put(env, output, "surfaces", static_cast<double>(surfaces)); return output;
    END
}
static napi_value acquire(napi_env env, napi_callback_info info) {
    BEGIN(1)
    auto* target = session(env, argv[0]); std::lock_guard<std::mutex> guard(target->mutex);
    Slot* selected = nullptr;
    for (auto& slot : target->slots) if (slot.owner == Ownership::Ready && (!selected || slot.frame > selected->frame)) selected = &slot;
    if (!selected) return undefined(env);
    // Only the newest completed frame is transferred. Older unleased frames
    // can now be reused without invalidating the selected frame's lease.
    for (auto& slot : target->slots) if (&slot != selected && slot.owner == Ownership::Ready) slot.owner = Ownership::Free;
    if (target->retryRender.exchange(false)) { target->resized = true; target->notify(); }
    selected->owner = Ownership::Leased; ++target->acquired;
    napi_value output; napi_create_object(env, &output);
    put(env, output, "frame", static_cast<double>(selected->frame));
    put(env, output, "width", static_cast<double>(selected->surface->width)); put(env, output, "height", static_cast<double>(selected->surface->height));
    void* handle = selected->surface->nativeHandle(); napi_value buffer;
    napiChecked(napi_create_buffer_copy(env, sizeof(handle), &handle, nullptr, &buffer)); napi_set_named_property(env, output, "handle", buffer);
    return output;
    END
}
static napi_value release(napi_env env, napi_callback_info info) {
    BEGIN(2)
    auto* target = session(env, argv[0]); double frame; napiChecked(napi_get_value_double(env, argv[1], &frame));
    std::lock_guard<std::mutex> guard(target->mutex);
    for (auto& slot : target->slots) if (slot.owner == Ownership::Leased && slot.frame == static_cast<uint64_t>(frame)) { slot.owner = Ownership::Free; ++target->released; }
    // A resize or final paused frame may have arrived while both slots were
    // occupied. Retry it when ownership returns, even without another decode.
    if (target->retryRender.exchange(false)) target->resized = true;
    target->notify();
    return undefined(env);
    END
}
static napi_value send(napi_env env, napi_callback_info info) {
    BEGIN(3)
    auto* target = session(env, argv[0]); const auto kind = text(env, argv[1]);
    target->enqueue({kind == "shaders", list(env, argv[2])}); return undefined(env);
    END
}
static napi_value resize(napi_env env, napi_callback_info info) {
    BEGIN(3)
    auto* target = session(env, argv[0]); uint32_t w, h; napiChecked(napi_get_value_uint32(env, argv[1], &w)); napiChecked(napi_get_value_uint32(env, argv[2], &h));
    if (!w || !h || w > 3840 || h > 2160) throw std::runtime_error("Render size outside prototype budget");
    target->width = w; target->height = h; target->resized = true; target->notify(); return undefined(env);
    END
}
static napi_value close(napi_env env, napi_callback_info info) {
    BEGIN(1)
    session(env, argv[0])->shutdown(); return undefined(env);
    END
}
static napi_value init(napi_env env, napi_value exports) {
    const napi_property_descriptor methods[] = {
        {"create", nullptr, create, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"state", nullptr, state, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"acquire", nullptr, acquire, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"release", nullptr, release, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"send", nullptr, send, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"resize", nullptr, resize, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"close", nullptr, close, nullptr, nullptr, nullptr, napi_default, nullptr},
    };
    napi_define_properties(env, exports, sizeof(methods) / sizeof(methods[0]), methods); return exports;
}
NAPI_MODULE(NODE_GYP_MODULE_NAME, init)
