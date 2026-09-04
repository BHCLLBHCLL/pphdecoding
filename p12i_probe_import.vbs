Set fso_ = CreateObject("Scripting.FileSystemObject")
Set out_ = fso_.CreateTextFile("D:/training/cgns/pphdecoding/p12i_probe_import.log", True)
out_.WriteLine "start"
On Error Resume Next
Set App_ = GetApplication()
out_.WriteLine "s001=" & CStr(Err.Number)
Err.Clear
Set Doc_ = App_.GetDocument
out_.WriteLine "s002=" & CStr(Err.Number)
Err.Clear
out_.WriteLine "proj=" & Doc_.GetProjectName & " err=" & CStr(Err.Number)
Err.Clear
Set SN7_ = Doc_.ImportPatchAsCAD("D:/training/cgns/cabdecoding/.pytest_tmp/test_export_stl_unchanged0/mesh.stl")
out_.WriteLine "s003=" & CStr(Err.Number)
Err.Clear
out_.WriteLine "sn7_alive=" & CStr(Not (SN7_ Is Nothing)) & " err=" & CStr(Err.Number)
Err.Clear
Set SN8_ = Doc_.ImportPatchAsCAD("D:/training/cgns/pphdecoding/_p12i_e2e/p12i_patch2_sample_cube.stl")
out_.WriteLine "s004=" & CStr(Err.Number)
Err.Clear
out_.WriteLine "sn8_alive=" & CStr(Not (SN8_ Is Nothing)) & " err=" & CStr(Err.Number)
Err.Clear
Set Parts_ = Doc_.GetParts
out_.WriteLine "s005=" & CStr(Err.Number)
Err.Clear
out_.WriteLine "parts_ub=" & CStr(UBound(Parts_)) & " err=" & CStr(Err.Number)
Err.Clear
out_.WriteLine "end"
out_.Close
