' pphdecoding P4-3: Disc/Overset SetPartsControl 录制锁定（COM 实测）
' 在宿主内执行；全部步骤逐条记录 err；结尾恢复 False 且不保存工程。
On Error Resume Next
Set fso_ = CreateObject("Scripting.FileSystemObject")
Set log_ = fso_.CreateTextFile("D:\training\cgns\pphdecoding\box_com_diag4.log", True)
Sub Step(msg)
  log_.WriteLine msg & " err=" & Err.Number & " " & Err.Description
  Err.Clear
End Sub
Set App_ = GetApplication()
If App_ Is Nothing Then Set App_ = CreateObject("scFLOWpre_Bx64net.Application.2025")
Set Doc_ = App_.GetDocument
Step "GetApplication/GetDocument"
Doc_.OpenProject "D:/training/cgns/pphdecoding/box.pph", False
Step "OpenProject"
Set Conditions_ = Doc_.GetConditions
Step "GetConditions"
Conditions_.SetPartsControl "Discontinuous", True
Step "SetPartsControl Discontinuous=True"
Conditions_.SetPartsControl "Overset", True
Step "SetPartsControl Overset=True"
Conditions_.SetPartsControl "Discontinuous", False
Step "SetPartsControl Discontinuous=False(restore)"
Conditions_.SetPartsControl "Overset", False
Step "SetPartsControl Overset=False(restore)"
log_.Close
