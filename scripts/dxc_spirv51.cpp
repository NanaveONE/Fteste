#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>
#include <cstdint>
#include <cwchar>
struct Guid { uint32_t a;uint16_t b,c;uint8_t d[8]; };
static constexpr Guid clsid={0x73e22d93,0xe6ce,0x47f3,{0xb5,0xbf,0xf0,0x66,0x4f,0x39,0xc1,0xb0}};
static constexpr Guid iid_compiler={0x228b4687,0x5a6a,0x4730,{0x90,0x0c,0x97,0x02,0xb2,0x20,0x3f,0x54}};
static constexpr Guid iid_result={0x58346cda,0xdde7,0x4497,{0x94,0x61,0x6f,0x87,0xaf,0x5e,0x06,0x59}};
struct DxcBuffer{const void* ptr;size_t size;unsigned encoding;};
struct Unknown{virtual int QueryInterface(const Guid&,void**)=0;virtual unsigned AddRef()=0;virtual unsigned Release()=0;};
struct Blob:Unknown { virtual void* GetBufferPointer()=0;virtual size_t GetBufferSize()=0;};
struct Result:Unknown { virtual int GetStatus(int*)=0;virtual int GetResult(Blob**)=0;virtual int GetErrorBuffer(Blob**)=0;};
struct Compiler:Unknown {virtual int Compile(const DxcBuffer*,const wchar_t* const*,uint32_t,void*,const Guid&,void**)=0;};
int main(int argc,char** argv){
 if(argc!=4){std::cerr<<"usage: dxc51 libdxcompiler.so input.hlsl output.spv\n";return 2;}
 std::ifstream in(argv[2],std::ios::binary);if(!in){perror(argv[2]);return 2;}
 std::string source{std::istreambuf_iterator<char>{in},{}};
 auto h=dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);if(!h){std::cerr<<dlerror()<<"\n";return 2;}
 auto entry=(int(*)(const Guid&,const Guid&,void**))dlsym(h,"DxcCreateInstance");
 Compiler* compiler=nullptr;
 int rc=entry(clsid,iid_compiler,(void**)&compiler);
 if(rc<0||!compiler){std::cerr<<"dxc create failed "<<rc<<"\n";return 2;}
 DxcBuffer b{source.data(),source.size(),65001};
 const wchar_t* args[]={L"-E",L"shaderMain",L"-T",L"vs_6_0",L"-spirv",L"-fspv-target-env=vulkan1.1",L"-D__spirv__=1",L"-DXENOS_VERTEX_SHADER=1",L"-HV",L"2021"};
 Result* result=nullptr;
 rc=compiler->Compile(&b,args,sizeof(args)/sizeof(*args),nullptr,iid_result,(void**)&result);
 if(rc<0||!result){std::cerr<<"compile call failed "<<rc<<"\n";return 2;}
 int status=0;result->GetStatus(&status);
 Blob* errors=nullptr;result->GetErrorBuffer(&errors);
 if(errors){std::cerr.write((char*)errors->GetBufferPointer(),errors->GetBufferSize());errors->Release();}
 if(status<0){std::cerr<<"dxc status "<<status<<"\n";return 1;}
 Blob* obj=nullptr;result->GetResult(&obj);
 if(!obj||obj->GetBufferSize()<16){std::cerr<<"missing object\n";return 2;}
 std::ofstream out(argv[3],std::ios::binary);out.write((char*)obj->GetBufferPointer(),obj->GetBufferSize());
 std::cout<<"SPIRV_OK "<<obj->GetBufferSize()<<" bytes\n";
 obj->Release();result->Release();compiler->Release();dlclose(h);return 0;
}
