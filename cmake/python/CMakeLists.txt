set(subdir_2  Modules)
set(subdir_3  Programs)

set(PYTHON_SOURCES
    ${SRC_DIR}/${subdir_${PY_VERSION_MAJOR}}/python.c
)

add_executable(python ${PYTHON_SOURCES})
set_property(
    TARGET python
    PROPERTY RUNTIME_OUTPUT_DIRECTORY ${BIN_BUILD_DIR}
    )

# Link against the shared libpython if it was built, otherwise use the static
# version.
if(BUILD_LIBPYTHON_SHARED)
    target_link_libraries(python libpython-shared)
else()
    target_link_libraries(python libpython-static)
    set_target_properties(python PROPERTIES
        COMPILE_DEFINITIONS Py_NO_ENABLE_SHARED
        ENABLE_EXPORTS ON
    )
endif()

if(MSVC)
    set_target_properties(python PROPERTIES LINK_FLAGS /STACK:2000000)
endif()

if(CMAKE_SYSTEM_NAME STREQUAL iOS)
    set_target_properties(python PROPERTIES MACOSX_BUNDLE OFF)
endif()

# Export target
set_property(GLOBAL APPEND PROPERTY PYTHON_TARGETS python)

install(TARGETS python
        EXPORT PythonTargets
        RUNTIME DESTINATION ${BIN_INSTALL_DIR}
        COMPONENT Runtime)

# See "is_python_build()" in sysconfig.py
add_custom_command(TARGET python PRE_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory ${BIN_BUILD_DIR}/${CMAKE_CFG_INTDIR}/Modules
    COMMAND ${CMAKE_COMMAND} -E touch ${BIN_BUILD_DIR}/${CMAKE_CFG_INTDIR}/Modules/Setup.local
    COMMENT "Creating '${BIN_INSTALL_DIR}/${CMAKE_CFG_INTDIR}/Modules/Setup.local'"
    )

if(WIN32)
    # See "get_config_h_filename()" in sysconfig.py
    add_custom_command(TARGET python POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E make_directory ${BIN_BUILD_DIR}/${CMAKE_CFG_INTDIR}/PC
        COMMAND ${CMAKE_COMMAND} -E copy_if_different ${SRC_DIR}/PC/pyconfig.h ${BIN_BUILD_DIR}/${CMAKE_CFG_INTDIR}/PC/pyconfig.h
        COMMENT "Copying 'pyconfig.h' to '${BIN_INSTALL_DIR}/${CMAKE_CFG_INTDIR}/PC'"
        )
endif()

if(UNIX AND PY_VERSION VERSION_GREATER "2.7.4")
    # Setup landmark allowing to run the interpreter from a build tree. See 'getpath.c' for details.
    set(_sysconfigdata_py "_sysconfigdata.py")
    if("${PY_VERSION}" VERSION_EQUAL "3.6.0" OR "${PY_VERSION}" VERSION_GREATER "3.6.0")
        # XXX Add support for _PYTHON_SYSCONFIGDATA_NAME env. variable
        set(MULTIARCH "")
        set(_sysconfigdata_py "_sysconfigdata_${ABIFLAGS}_${PY_PLATFORM}_${MULTIARCH}.py")
    endif()
    if(CMAKE_SYSTEM_NAME STREQUAL iOS)
        add_custom_target(update_sysconfig ALL DEPENDS python)
        message(STATUS "Executing ${PYTHON_WRAPPER_COMMAND} ${CMAKE_CROSSCOMPILING_EMULATOR} $<TARGET_FILE:python> -E -S -m sysconfig --generate-posix-vars")
        if(CMAKE_OSX_ARCHITECTURES STREQUAL x86_64)
            add_custom_command(TARGET update_sysconfig POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E make_directory ${PROJECT_BINARY_DIR}/include/python${LD_VERSION}
            COMMAND ${CMAKE_COMMAND} -E copy_if_different ${PYCONFIG_BUILD_DIR}/pyconfig.h ${PROJECT_BINARY_DIR}/include/python${LD_VERSION}/pyconfig.h
            COMMAND ${CMAKE_COMMAND} -E make_directory ${PROJECT_BINARY_DIR}/lib/python${LIBPYTHON_VERSION}/config-${LD_VERSION}
            COMMAND ${CMAKE_COMMAND} -E copy_if_different ${BIN_BUILD_DIR}/Makefile ${PROJECT_BINARY_DIR}/lib/python${LIBPYTHON_VERSION}/config-${LD_VERSION}/Makefile
            COMMAND ${CMAKE_COMMAND} -E env SIMCTL_CHILD_PYTHONHOME=${PROJECT_BINARY_DIR} ${CMAKE_CROSSCOMPILING_EMULATOR} $<TARGET_FILE:python> -S -m sysconfig --generate-posix-vars
            COMMENT "Relocate ${_sysconfigdata_py} and update pybuilddir.txt"
            WORKING_DIRECTORY ${BIN_BUILD_DIR}
            )
        endif()
        if(DEFINED IOS_CORESIM_PATH)
            add_custom_command(TARGET update_sysconfig POST_BUILD
            COMMAND ${CMAKE_COMMAND}
              -DBIN_BUILD_DIR:PATH=${IOS_CORESIM_PATH}
              -DSYSCONFIGDATA_PY:STRING=${_sysconfigdata_py}
              -DPYTHON_BINARY_DIR:PATH=${PROJECT_BINARY_DIR}
              -DEXTENSION_INSTALL_DIR:PATH=${EXTENSION_INSTALL_DIR}
              -P ${PROJECT_SOURCE_DIR}/cmake/UpdateSysconfig.cmake
            COMMENT "Relocate ${_sysconfigdata_py} and update pybuilddir.txt"
            WORKING_DIRECTORY ${IOS_CORESIM_PATH}
            )
            install(FILES ${EXTENSION_BUILD_DIR}/${_sysconfigdata_py}
                DESTINATION ${PYTHONHOME}/)
        endif()
    else()
        add_custom_command(
        OUTPUT ${BIN_BUILD_DIR}/pybuilddir.txt ${EXTENSION_BUILD_DIR}/${_sysconfigdata_py}
        COMMAND ${PYTHON_WRAPPER_COMMAND}
          ${CMAKE_CROSSCOMPILING_EMULATOR} $<TARGET_FILE:python> -E -S -m sysconfig --generate-posix-vars
        COMMAND ${CMAKE_COMMAND}
          -DBIN_BUILD_DIR:PATH=${BIN_BUILD_DIR}
          -DSYSCONFIGDATA_PY:STRING=${_sysconfigdata_py}
          -DPYTHON_BINARY_DIR:PATH=${PROJECT_BINARY_DIR}
          -DEXTENSION_INSTALL_DIR:PATH=${EXTENSION_INSTALL_DIR}
          -P ${PROJECT_SOURCE_DIR}/cmake/UpdateSysconfig.cmake
        COMMENT "Relocate ${_sysconfigdata_py} and update pybuilddir.txt"
        WORKING_DIRECTORY ${BIN_BUILD_DIR}
        DEPENDS python
        )
        add_custom_target(update_sysconfig ALL
            DEPENDS ${BIN_BUILD_DIR}/pybuilddir.txt ${EXTENSION_BUILD_DIR}/${_sysconfigdata_py}
            )
        install(FILES ${EXTENSION_BUILD_DIR}/${_sysconfigdata_py}
            DESTINATION ${PYTHONHOME}/)
    endif()
endif()

if(UNIX AND NOT CMAKE_CROSSCOMPILING)
  install(CODE
"message(STATUS \"Creating Python executable symlinks...\")
execute_process(
  COMMAND \${CMAKE_COMMAND} -E create_symlink python
    python${PY_VERSION_MAJOR}
  COMMAND \${CMAKE_COMMAND} -E create_symlink python
    python${PY_VERSION_MAJOR}.${PY_VERSION_MINOR}
  WORKING_DIRECTORY
    \$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}/${BIN_INSTALL_DIR}
  )"
)
endif()

# Copy up the gdb python hooks into a position where they can be automatically
# loaded by gdb during Lib/test/test_gdb.py
#
# Distributors are likely to want to install this somewhere else e.g. relative
# to the stripped DWARF data for the shared library.

set(SRC_GDB_HOOKS ${SRC_DIR}/Tools/gdb/libpython.py)
configure_file(
    ${SRC_GDB_HOOKS}
    ${BIN_BUILD_DIR}/libpython.py
    COPYONLY
)
if(INSTALL_DEVELOPMENT)
    install(FILES ${SRC_GDB_HOOKS} DESTINATION ${BIN_INSTALL_DIR} COMPONENT Development)
endif()
