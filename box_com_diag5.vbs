' pphdecoding P4-4: 生成黄金文件集变体（COM 宿主内执行）
' box_disc.pph    = box.pph + SetPartsControl Discontinuous True
' box_overset.pph = box.pph + SetPartsControl Overset True
' 原工程不保存（结束前恢复 False）。
On Error Resume Next
Set fso_ = CreateObject("Scripting.FileSystemObject")
Set log_ = fso_.CreateTextFile("D:\training\cgns\pphdecoding\box_com_diag5.log", True)
Sub Step(msg)
  log_.WriteLine msg & " err=" & Err.Number & " " & Err.Description
  Err.Clear
End Sub
Set App_ = GetApplication()
If App_ Is Nothing Then Set App_ = CreateObject("scFLOWpre_Bx64net.Application.2025")
Set Doc_ = App_.GetDocument
Step "GetApplication/GetDocument"
Doc_.OpenProject "D:/training/cgns/pphdecoding/box.pph", False
Step "OpenProject box"
Set Conditions_ = Doc_.GetConditions
Step "GetConditions"

Conditions_.SetPartsControl "Discontinuous", True
Step "SetPartsControl Discontinuous=True"
Doc_.SaveProject "D:/training/cgns/pphdecoding/tests/box_disc.pph"
Step "SaveProject box_disc"

Conditions_.SetPartsControl "Discontinuous", False
Step "SetPartsControl Discontinuous=False"
Conditions_.SetPartsControl "Overset", True
Step "SetPartsControl Overset=True"
Doc_.SaveProject "D:/training/cgns/pphdecoding/tests/box_overset.pph"
Step "SaveProject box_overset"

Conditions_.SetPartsControl "Overset", False
Step "SetPartsControl Overset=False(restore)"
Doc_.CloseProject False
Step "CloseProject(no save)"
log_.Close
