/*
Copyright (c) 2015-2018 by the parties listed in the AUTHORS file.
All rights reserved.  Use of this source code is governed by 
a BSD-style license that can be found in the LICENSE file.
*/

#ifndef TOAST_MEMORY_HPP
#define TOAST_MEMORY_HPP

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wattributes"

#if !defined(do_pragma)
#define do_pragma(x) _Pragma(#x)
#endif

#if defined(__GNUC__) && (defined(__x86_64__) || defined(__x86_64)) && \
    !defined(__INTEL_COMPILER)
#   define attrib_aligned __attribute__((aligned (64)))
#   define attrib_assume_aligned __attribute__((assume_aligned(64)))
#else
#   define attrib_aligned __attribute__((aligned (64)))
#   define attrib_assume_aligned
#endif

namespace toast { namespace mem {

    // Byte alignment for SIMD.  This should work for all modern systems, 
    // including MIC
    static size_t const SIMD_ALIGN = 64;

    void * aligned_alloc ( size_t size, size_t align );
    void aligned_free ( void * ptr );
  
    template < typename T >
    class simd_allocator {

        public :

            // type definitions
            typedef T value_type;
            typedef T * pointer;
            typedef T const * const_pointer;
            typedef T & reference;
            typedef T const & const_reference;
            typedef std::size_t size_type;
            typedef std::ptrdiff_t difference_type;

            // rebind allocator to type U
            template < typename U >
            struct rebind {
                typedef simd_allocator < U > other;
            };

            // return address of values
            pointer address ( reference value ) const {
                return &value;
            }

            const_pointer address ( const_reference value ) const {
                return &value;
            }

            simd_allocator ( ) throw() { }

            simd_allocator ( simd_allocator const & ) throw() { }

            template < typename U >
            simd_allocator ( simd_allocator < U > const & ) throw() { }

            ~simd_allocator ( ) throw() { }

            // return maximum number of elements that can be allocated
            size_type max_size() const throw() {
                return std::numeric_limits < std::size_t > :: max() / sizeof(T);
            }

            // allocate but don't initialize num elements of type T
            pointer allocate ( size_type const num, const void *hint=0 ) {
                pointer align_ptr = static_cast < pointer > ( aligned_alloc ( num * sizeof(T), SIMD_ALIGN ) );
                return align_ptr;
            }

            // initialize elements of allocated storage p with value value
            void construct ( pointer p, T const & value ) {
                // initialize memory with placement new
                new ( static_cast < void * > (p) ) T(value);
            }

            // destroy elements of initialized storage p
            void destroy ( pointer p ) {
                // destroy objects by calling their destructor
                p->~T();
            }

            // deallocate storage p of deleted elements
            void deallocate ( pointer p, size_type num ) {
                aligned_free ( static_cast < void * > (p) );
            }

    };

    // return that all specializations of this allocator are interchangeable
    template < typename T1, class T2 >
    bool operator == ( simd_allocator < T1 > const &, simd_allocator < T2 > const & ) throw() {
        return true;
    }

    template < typename T1, class T2 >
    bool operator != ( simd_allocator < T1 > const &, simd_allocator < T2 > const & ) throw() {
        return false;
    }

    //========================================================================//
    // cleaner version of:
    //     double* var = static_cast<double*>(toast::mem::aligned_alloc(
    //              n * sizeof(double), toast::mem::SIMD_ALIGN ) );

    template <typename _Tp>
    _Tp* simd_alloc(size_t n)
    {
        return static_cast<_Tp*>(toast::mem::aligned_alloc(n * sizeof(_Tp),
                                                           toast::mem::SIMD_ALIGN));
    }

    //========================================================================//
    // template class for memory-aligned c-style array with internal
    // allocation and deallocation
    template <typename _Tp>
    class simd_array
    {
    public:
        typedef std::size_t size_type;

#if defined(__INTEL_COMPILER) && (defined(__x86_64__) || defined(__x86_64))
        typedef _Tp* __attribute__((align_value(64))) _Tptr;
#else
        typedef _Tp* _Tptr;
#endif

    public:
        simd_array()
        : m_data(nullptr)
        { }

        simd_array(size_type _n)
        : m_data(toast::mem::simd_alloc<_Tp>(_n))
        { }

        simd_array(size_type _n, const _Tp& _init)
        : m_data(toast::mem::simd_alloc<_Tp>(_n))
        {
            for(size_type i = 0; i < _n; ++i)
                m_data[i] = _init;
        }

        ~simd_array() { toast::mem::aligned_free(m_data); }

        // conversion function to _Tp*
        operator _Tptr() attrib_assume_aligned
        { return m_data; }

        simd_array& operator=(const simd_array& rhs)
        {
            if(this != &rhs)
            {
                if(m_data)
                    toast::mem::aligned_free(m_data);
                m_data = static_cast<_Tp*>(rhs.m_data);
                // otherwise will be deleted
                const_cast<simd_array&>(rhs).m_data = nullptr;
            }
            return *this;
        }

    private:
        _Tp* m_data;

    } attrib_aligned;

    //========================================================================//

} }

#pragma GCC diagnostic pop

#endif

