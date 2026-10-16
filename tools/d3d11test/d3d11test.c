/*
 * d3d11test: minimal Direct3D 11 smoke test for a bottle.
 *
 * Creates a window and swap chain, clears the back buffer to a known colour,
 * reads one pixel back through a staging texture and presents for a few
 * seconds. Prints adapter, feature level, which d3d11.dll was loaded and
 * PASS/FAIL to stdout.
 *
 * Build: x86_64-w64-mingw32-gcc -O2 -s -o d3d11test.exe d3d11test.c -ld3d11 -ldxgi -luuid -mwindows
 */
#define COBJMACROS
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <stdio.h>

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    if (m == WM_DESTROY) { PostQuitMessage(0); return 0; }
    return DefWindowProcW(h, m, w, l);
}

static void pump(void)
{
    MSG msg;
    while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
}

int main(int argc, char **argv)
{
    int seconds = argc > 1 ? atoi(argv[1]) : 5;
    const float color[4] = { 0.2f, 0.6f, 0.9f, 1.0f }; /* expect ~ (51,153,229) */

    WNDCLASSW wc = { 0 };
    wc.lpfnWndProc = wndproc;
    wc.hInstance = GetModuleHandleW(NULL);
    wc.lpszClassName = L"d3d11test";
    wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    RegisterClassW(&wc);
    HWND hwnd = CreateWindowW(L"d3d11test", L"openbottle D3D11 test", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                              100, 100, 640, 400, NULL, NULL, wc.hInstance, NULL);
    if (!hwnd) { printf("FAIL: CreateWindow\n"); return 1; }

    DXGI_SWAP_CHAIN_DESC sd = { 0 };
    sd.BufferCount = 2;
    sd.BufferDesc.Width = 640;
    sd.BufferDesc.Height = 400;
    sd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.OutputWindow = hwnd;
    sd.SampleDesc.Count = 1;
    sd.Windowed = TRUE;
    sd.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;

    ID3D11Device *dev = NULL;
    ID3D11DeviceContext *ctx = NULL;
    IDXGISwapChain *sc = NULL;
    D3D_FEATURE_LEVEL fl = 0;
    HRESULT hr = D3D11CreateDeviceAndSwapChain(NULL, D3D_DRIVER_TYPE_HARDWARE, NULL, 0, NULL, 0,
                                               D3D11_SDK_VERSION, &sd, &sc, &dev, &fl, &ctx);
    if (FAILED(hr)) { printf("FAIL: D3D11CreateDeviceAndSwapChain hr=0x%08lx\n", hr); return 1; }

    wchar_t path[MAX_PATH] = L"?";
    GetModuleFileNameW(GetModuleHandleW(L"d3d11.dll"), path, MAX_PATH);
    printf("d3d11.dll: %ls\n", path);
    printf("feature level: 0x%x\n", fl);

    IDXGIDevice *dxgidev = NULL;
    IDXGIAdapter *adapter = NULL;
    DXGI_ADAPTER_DESC ad;
    if (SUCCEEDED(ID3D11Device_QueryInterface(dev, &IID_IDXGIDevice, (void **)&dxgidev)) &&
        SUCCEEDED(IDXGIDevice_GetAdapter(dxgidev, &adapter)) &&
        SUCCEEDED(IDXGIAdapter_GetDesc(adapter, &ad)))
        printf("adapter: %ls (vendor 0x%04x)\n", ad.Description, ad.VendorId);

    ID3D11Texture2D *back = NULL;
    ID3D11RenderTargetView *rtv = NULL;
    IDXGISwapChain_GetBuffer(sc, 0, &IID_ID3D11Texture2D, (void **)&back);
    ID3D11Device_CreateRenderTargetView(dev, (ID3D11Resource *)back, NULL, &rtv);

    /* Clear and read one pixel back. */
    ID3D11DeviceContext_ClearRenderTargetView(ctx, rtv, color);
    D3D11_TEXTURE2D_DESC td;
    ID3D11Texture2D_GetDesc(back, &td);
    td.Usage = D3D11_USAGE_STAGING;
    td.BindFlags = 0;
    td.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    td.MiscFlags = 0;
    ID3D11Texture2D *staging = NULL;
    int pass = 0;
    if (SUCCEEDED(ID3D11Device_CreateTexture2D(dev, &td, NULL, &staging))) {
        ID3D11DeviceContext_CopyResource(ctx, (ID3D11Resource *)staging, (ID3D11Resource *)back);
        D3D11_MAPPED_SUBRESOURCE map;
        if (SUCCEEDED(ID3D11DeviceContext_Map(ctx, (ID3D11Resource *)staging, 0, D3D11_MAP_READ, 0, &map))) {
            unsigned char *p = (unsigned char *)map.pData + map.RowPitch * 200 + 4 * 320;
            printf("pixel(320,200): %u %u %u %u\n", p[0], p[1], p[2], p[3]);
            pass = abs(p[0] - 51) <= 2 && abs(p[1] - 153) <= 2 && abs(p[2] - 229) <= 2;
            ID3D11DeviceContext_Unmap(ctx, (ID3D11Resource *)staging, 0);
        }
    }

    /* Present frames so the window shows the colour. */
    DWORD end = GetTickCount() + seconds * 1000;
    int frames = 0;
    while (GetTickCount() < end) {
        pump();
        ID3D11DeviceContext_OMSetRenderTargets(ctx, 1, &rtv, NULL);
        ID3D11DeviceContext_ClearRenderTargetView(ctx, rtv, color);
        if (FAILED(IDXGISwapChain_Present(sc, 1, 0))) { printf("FAIL: Present\n"); pass = 0; break; }
        frames++;
    }
    printf("frames presented: %d\n", frames);
    printf("%s\n", pass ? "PASS" : "FAIL");
    fflush(stdout);
    return pass ? 0 : 2;
}
