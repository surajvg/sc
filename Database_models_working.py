
# from sqlalchemy import Column,Integer,String,Float,DateTime,ForeignKey,Date,LargeBinary,Boolean
# from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import relationship
# from datetime import date, datetime

# from sqlalchemy import (
#     create_engine, Column, Integer, String, ForeignKey,JSON, and_,
#     select, DateTime, func, or_,Identity
# )
# base  = declarative_base()

# class UserProfile(base):
#     __tablename__ = "userProfiles"
#     userID = Column(String, primary_key=True)
#     username = Column(String)
#     userRole = Column(String)
#     admin = Column(String)
#     sbu = Column(String)
#     subdivision = Column(String)
#     description = Column(String)
#     company = Column(String)
#     password = Column(String)
#     createdAt = Column(DateTime(timezone=True))
#     updatedAt = Column(DateTime(timezone=True))

# class QRRecord_db(base):
#     __tablename__ = "qr_records"

#     Reference_No= Column(String, primary_key = True, index=True)
#     Timestamp = Column(DateTime)
#     SL_No = Column(Integer, autoincrement=True) 
#     BEL_Part_Number = Column(String)
#     MPN= Column(String)
#     Batch_Lot_No= Column(String)
#     DateCode= Column(String)
#     Quantity= Column(String)
#     BEL_PO_No= Column(String)
#     Vendor_Name= Column(String)
#     OEM_Make= Column(String)
#     Manufacturing_Place= Column(String)
#     GR_No= Column(String)
#     GR_Date= Column(DateTime)
    
#     Description = Column(String)
#     Vendor_Code = Column(String)
#     Invoice_No  = Column(String)
#     Invoice_Dt = Column(DateTime)

# class LogBook_db(base):
#     __tablename__ = "log_book"
    
#     SL_No = Column(Integer, primary_key=True, autoincrement=True, index=True)
#     Timestamp = Column(DateTime )
#     BEL_Part_Number = Column(String )
#     MPN = Column(String )
#     Batch_Lot_No = Column(String )
#     DateCode = Column(String )
#     Quantity = Column(String )
#     BEL_PO_No = Column(String )
#     Vendor_Name = Column(String )
#     OEM_Make = Column(String )
#     Manufacturing_Place = Column(String)

# class RoutingCard(base):
#     __tablename__ = "Fab_RoutingCard"

#     Id = Column(Integer, primary_key=True, index=True)
#     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
#     BEL_PO_No = Column(Integer)  
#     Vendor_Name = Column(String)
#     Description = Column(String)  
#     Record_Date = Column(String, default=datetime.now)       
#     Quantity = Column(Integer)
#     Invoice_No = Column(String)
#     Invoice_Dt = Column(DateTime)
             
#     No_of_Cases = Column(Integer)
#     Location = Column(String)

#     GR_No = Column(String)
#     GR_Date = Column(DateTime)

# class QRRecord_Generated(base):
#     __tablename__ = "generated_qr_records"

#     inspection_type = Column(String, nullable=True)

#     Timestamp = Column(DateTime)
#     SL_No = Column(Integer) 
#     BEL_Part_Number = Column(String)
#     MPN= Column(String)
#     Batch_Lot_No= Column(String)
#     DateCode= Column(String)
#     Quantity= Column(String)
#     BEL_PO_No= Column(String)
#     Vendor_Name= Column(String)
#     OEM_Make= Column(String)
#     Manufacturing_Place= Column(String)
#     GR_No= Column(String)
#     GR_Date= Column(DateTime)
#     Reference_No= Column(String, primary_key = True, index=True)
#     Description = Column(String)
#     Vendor_Code = Column(String)
#     Invoice_No  = Column(String)
#     Invoice_Dt = Column(DateTime)
#     Status = Column(String)
#     overall_status = Column(String,default="Generated")

#     userID = Column(String)
#     userName = Column(String)
#     userRole = Column(String)
#     userSBU = Column(String)
#     userSBUDIV = Column(String)

#     subcontracts = relationship("SubContract_Inspection", back_populates="qr_record", cascade="all, delete-orphan")
#     dimensions = relationship("DimensionReport", back_populates="qr_record",cascade="all, delete-orphan")
#     dimension_common_reports = relationship("DimensionCommonReport", back_populates="reference", cascade="all, delete-orphan")
#     intender_report = relationship("Intender_Report", back_populates="qr_record",cascade="all, delete-orphan")
#     Submission_Details = relationship("Authorized_Person", back_populates="qr_record",cascade="all, delete-orphan")
#     instrument = relationship("Measuring_Instruments_Used", back_populates="qr_record",cascade="all, delete-orphan")

    
# class DimensionInstrumentMap(base):
#     __tablename__ = "dimension_instrument_map"

#     Id = Column(Integer, primary_key=True, index=True)

#     Report_Id = Column(Integer, ForeignKey("dimension_reports.Id"))
#     Instrument_Id = Column(Integer, ForeignKey("measuring_instruments.Equipment_ID"))

#     # Relationships
#     report = relationship("DimensionReport", back_populates="instrument_links")
#     instrument = relationship("Measuring_Instruments", back_populates="report_links")

# class Measuring_Instruments(base):
#     __tablename__ = "measuring_instruments"

#     Description = Column(String)
#     Equipment_ID = Column(Integer, primary_key=True, index=True)
#     Measuring_Accuracy = Column(Float)
#     Make_Model = Column(String)
#     Cal_Date = Column(DateTime)
#     Due_Date = Column(DateTime)

#     report_links = relationship(
#         "DimensionInstrumentMap",
#         back_populates="instrument",
#         cascade="all, delete-orphan"
#     )
#     instruments = relationship(
#         "Measuring_Instruments_Used",
#         back_populates="instrument_used",
#         cascade="all, delete-orphan"
#     )

# class SubContract_Inspection(base):
#     __tablename__ = "subcontract_inspection"

#     SAN_NO = Column(Integer, primary_key=True, index=True)
#     Control_No = Column(Integer)

#     # Basic details (common in both tables)
#     Part_No = Column(String)
#     Description = Column(String)
#     PO_NO = Column(String)
#     Vendor_Name = Column(String)
#     Quantity = Column(String)
#     Sample = Column(String)
#     Sale_Order = Column(String)
#     Drg_Issue_Level = Column(Integer)

#     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
#     Date = Column(Date, default=date.today)

#     userID = Column(String)
#     userName = Column(String)
#     userRole = Column(String)
#     userSBU = Column(String)
#     userSBUDIV = Column(String)

#     # Report section (only in second table)
#     Vendor_Dimension_Report = Column(String, nullable=True)
#     Visual_Inspection = Column(String, nullable=True)
#     Raw_Material_Supplied = Column(String, nullable=True)
#     Raw_Material_Test_Report = Column(String, nullable=True)
#     # Relationship
#     qr_record = relationship("QRRecord_Generated", back_populates="subcontracts")

# # class Dimension_Report(base):
# #     __tablename__ = "dimension_report"
# #     id = Column(Integer,primary_key=True,index=True)
# #     Basic_Dimension = Column(Float)
# #     Measuring_Instr_Id = Column(Integer, ForeignKey("measuring_instruments.Id"))
# #     Tolerance = Column(Float)
# #     Min = Column(Float)
# #     Max = Column(Float)
# #     Sample_1 = Column(Float,nullable=True)
# #     Sample_2 = Column(Float,nullable=True)
# #     Sample_3 = Column(Float,nullable=True)
# #     Sample_4 = Column(Float,nullable=True)
# #     Sample_5 = Column(Float,nullable=True)
# #     Sample_6= Column(Float,nullable=True)
# #     Sample_7 = Column(Float,nullable=True)
# #     Sample_8 = Column(Float,nullable=True)
# #     Sample_9 = Column(Float,nullable=True)
# #     Sample_10 = Column(Float,nullable=True)
# #     Sample_11 = Column(Float,nullable=True)
# #     Sample_12 = Column(Float,nullable=True)
# #     Sample_13 = Column(Float,nullable=True)
# #     Sample_14 = Column(Float,nullable=True)
# #     Sample_15 = Column(Float,nullable=True)

# #     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
# #     qr_record = relationship("QRRecord_Generated", back_populates="dimensions")
# #     measurement = relationship("Measuring_Instruments", back_populates="dimension")



# class DimensionType(base):
#     __tablename__ = "dimension_types"

#     Id = Column(Integer, primary_key=True, index=True)
#     Name = Column(String, nullable=False)

#     reports = relationship("DimensionReport", back_populates="dimension_type")
    

# # -------------------------------
# # 2. Dimension Report (Per Dimension Per Reference_No)
# # -------------------------------
# class DimensionReport(base):
#     __tablename__ = "dimension_reports"

#     Id = Column(Integer, primary_key=True, index=True)
#     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
#     Dimension_Type_Id = Column(Integer, ForeignKey("dimension_types.Id"))

#     Basic_Dimension = Column(Float)
#     Tolerance = Column(Float)
#     Min = Column(Float)
#     Max = Column(Float)
#     dimension_type = relationship("DimensionType", back_populates="reports")
#     qr_record = relationship("QRRecord_Generated", back_populates="dimensions")

#     samples = relationship("DimensionSample", back_populates="report",
#                            cascade="all, delete-orphan")
#     instrument_links = relationship(
#         "DimensionInstrumentMap",
#         back_populates="report",
#         cascade="all, delete-orphan"
#     )

    
# # -------------------------------
# # 3. Dimension Samples (Values Entered by User)
# # -------------------------------
# class DimensionSample(base):
#     __tablename__ = "dimension_samples"

#     Id = Column(Integer, primary_key=True, index=True)
#     Report_Id = Column(Integer, ForeignKey("dimension_reports.Id"))
#     Sample_No = Column(Integer)  # 1 to 15
#     Value = Column(Float)
#     Status = Column(String)  # OK / NOT OK
#     Remarks = Column(String,nullable=True)
#     Dimension_View_Parameter = Column(String,nullable=True)
#     Dimension_Parameter_Unit = Column(String)
    
#     report = relationship("DimensionReport", back_populates="samples")


# class DimensionCommonReport(base):
#     __tablename__ = "dimension_common_report"

#     Id = Column(Integer, primary_key=True, index=True)
#     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))


    
#     Remarks = Column(String, nullable=True)

#     Marking_On_Material = Column(String, nullable=True)
#     Dimension_Remark = Column(String, nullable=True)
#     Visual_Inspection_Report = Column(String, nullable=True)
#     Electrical_Inspection_Remark = Column(String, nullable=True)
#     Electrical_Parameter = Column(String, nullable=True)
#     Functional = Column(String, nullable=True)
#     Dimensions = Column(String, nullable=True)
#     Visual_Inspection = Column(String, nullable=True)
#     COC = Column(String, nullable=True)
#     Test_Reports = Column(String, nullable=True)
#     Imported_Doc_Received = Column(String, nullable=True)
#     Malware_Free_Cert = Column(String, nullable=True)
#     FOD_Check = Column(String, nullable=True)
#     Counterfeit_Checked = Column(String, nullable=True)
#     MFG_Date = Column(Date, nullable=True)
#     Exp_Date = Column(Date, nullable=True)
#     Qty_Received = Column(String, nullable=True)
#     Qty_Inspected = Column(String, nullable=True)
#     Qty_Accepted = Column(String, nullable=True)
#     Qty_Rejected = Column(String, nullable=True)


#     Inspection_Remarks = Column(String, nullable=True)

#     userID = Column(String)
#     userName = Column(String)
#     userRole = Column(String)
#     userSBU = Column(String)
#     userSBUDIV = Column(String)

#     # Links all DimensionReports for this reference
#     reference = relationship("QRRecord_Generated", back_populates="dimension_common_reports")


# class Intender_Report(base):
#     __tablename__ = "intender_report"

#     Id = Column(Integer, primary_key=True, index=True)
#     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
#     Project_SaleOrder = Column(String)  # 1 to 15
#     Result = Column(String)
#     Serial_Numbers = Column(String)  # OK / NOT OK
#     Remarks = Column(String)
#     Date = Column(Date)
#     Status = Column(String)

#     userID = Column(String)
#     userName = Column(String)
#     userRole = Column(String)
#     userSBU = Column(String)
#     userSBUDIV = Column(String)
    
#     qr_record = relationship("QRRecord_Generated", back_populates="intender_report")



# class Authorized_Person(base):
#     __tablename__ = 'user_data'
    
#     id = Column(Integer, primary_key=True)
#     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"),nullable=False)

#     insUserID = Column(String,nullable=False)
#     insUserName = Column(String) 
#     insUserRole = Column(String)
#     insUserSBU = Column(String)
#     insUserSBUDIV = Column(String)
#     insDate = Column(Date,default=date.today)

#     insfilename = Column(String)
#     insmimetype = Column(String)
#     insdata = Column(LargeBinary)

#     insRemarks = Column(String)

#     appUserID = Column(String,nullable=True)
#     appUserName = Column(String,nullable=True)
#     appUserRole = Column(String,nullable=True)
#     appUserSBU = Column(String,nullable=True)
#     appUserSBUDIV = Column(String,nullable=True)

#     appfilename = Column(String,nullable=True)
#     appmimetype = Column(String,nullable=True)
#     appdata = Column(LargeBinary,nullable=True)

#     appDate = Column(Date,nullable=True)
#     appRemarks = Column(String,nullable=True)


#     # Staff_No = Column(Integer) #userID
#     # Name = Column(String)
#     # Role = Column(String)
#     # Date = Column(Date,default=date.today)


#     qr_record = relationship("QRRecord_Generated", back_populates="Submission_Details")


# # class Authorized_Person(base):
# #     __tablename__ = 'user_data'
    
# #     id = Column(Integer, primary_key=True)
# #     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"), nullable=False)

# #     insUserID = Column(String, nullable=False)
# #     insUserName = Column(String) 
# #     insUserRole = Column(String)
# #     insUserSBU = Column(String)
# #     insUserSBUDIV = Column(String)
# #     insDate = Column(Date, default=date.today)
# #     insfilename = Column(String)
# #     insmimetype = Column(String)
# #     insdata = Column(LargeBinary)
# #     insRemarks = Column(String)

# #     appUserID = Column(String, nullable=True)
# #     appUserName = Column(String, nullable=True)
# #     appUserRole = Column(String, nullable=True)
# #     appUserSBU = Column(String, nullable=True)
# #     appUserSBUDIV = Column(String, nullable=True)

# #     appfilename = Column(String, nullable=True)
# #     appmimetype = Column(String, nullable=True)
# #     appdata = Column(LargeBinary, nullable=True)

# #     appDate = Column(Date, nullable=True) 
# #     appRemarks = Column(String, nullable=True)
    




# class Measuring_Instruments_Used(base):
#     __tablename__ = "measuring_instrument_used"

#     id = Column(Integer,primary_key=True)
#     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
#     Equipment_ID = Column(Integer, ForeignKey("measuring_instruments.Equipment_ID"))

#     qr_record = relationship("QRRecord_Generated", back_populates="instrument")
#     instrument_used = relationship(
#         "Measuring_Instruments",
#         back_populates="instruments"
#     )

# class Indenter(base):
#     __tablename__ = "indenter_table"

#     indId = Column(Integer, primary_key=True)
#     userID = Column(String, ForeignKey("userProfiles.userID"))
#     # indUserID = Column(String)
#     # indUserName = Column(String)
#     # indUserRole = Column(String)
#     # indUserSBU = Column(String)
#     # indUserSBUDIV = Column(String)
#     # indPhoneNo = Column(String)
#     # date = Column(Date)
#     user = relationship("UserProfile")

# class IndenterApproval(base):
#     __tablename__ = "indenter_approval_details"

#     id = Column(Integer, primary_key=True)
#     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
#     serialNo = Column(String)

#     indUserID = Column(String)
#     indUserName = Column(String)
#     indUserRole = Column(String, default="Indentor")
#     indUserSBU = Column(String)
#     indUserSBUDIV = Column(String)
#     indPhoneNo = Column(String)
#     date = Column(Date)
    
#     insUserID = Column(String)
#     insUserName = Column(String)
#     insUserRole = Column(String)
#     insUserSBU = Column(String)
#     insUserSBUDIV = Column(String)

#     Status = Column(String)



# class MaterialInspection(base):
#     __tablename__ = "material_inspection"

#     id = Column(Integer, primary_key=True)
#     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))

#     Batch_Lot_No = Column(String)
#     Description = Column(String)
#     Revision_Level = Column(String)
#     Valuation_Type = Column(String)
#     Storage_Location = Column(String)
#     SO_Number = Column(String)
#     Project = Column(String)
#     Plant = Column(String)
#     PO_Number = Column(String)
#     GR_Number = Column(String)
#     GR_Date = Column(String)
#     Vendor_Name = Column(String)
#     Ins_start_date = Column(Date,nullable=True)
#     Ins_end_date = Column(Date,nullable=True)
#     Test_eq_text = Column(String)
#     Ins_Lot_Status = Column(String)

#             # Control_No=next_control,
#             # SAN_NO=next_san,
#             # Part_No=qr.BEL_Part_Number,
#             # Description=qr.Description,
#             # PO_NO=qr.BEL_PO_No, - present
#             # Vendor_Name=qr.Vendor_Name,- present
#             # Quantity=qr.Quantity,
#             # Sample="5 Nos",
#             # Sale_Order="SO-1234", - present
#             # Drg_Issue_Level=1, 
#             # Reference_No=qr.Reference_No, - present
#             # Date=date.today() - present
    
#     insUserID = Column(String)
#     insUserName = Column(String)
#     insUserRole = Column(String)
#     insUserSBU = Column(String)
#     insUserSBUDIV = Column(String)

# class MaterialTables(base):
#     __tablename__ = "material_table"

#     id = Column(Integer,primary_key=True)
#     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
    
#     Type = Column(String)
#     MIC_No = Column(Integer, nullable=True)	
#     MIC	= Column(String, nullable=True)
#     MIC_Desc = Column(String, nullable=True)
#     Sampling_Procedure = Column(String, nullable=True)
#     Sampling_Qty = Column(String, nullable=True)	
#     Inspected_Qty = Column(String, nullable=True)
#     UoM	= Column(String, nullable=True)
#     TargetValue	= Column(String, nullable=True)
#     LowerLimit = Column(String, nullable=True)
#     UpperLimit	= Column(String, nullable=True)
#     SampleNo = Column(Integer, nullable=True)	
#     Result = Column(String, nullable=True)
#     Valuation = Column(String, nullable=True)
#     InspDate = Column(Date, nullable=True)
#     Remarks = Column(String, nullable=True)


# class MaterialSummary(base):
#     __tablename__ = "materialsummary"

#     id = Column(Integer,primary_key=True)
#     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))

#     qty_blocked = Column(Integer, nullable=True)
#     qty_returned = Column(Integer, nullable=True)
#     UD_Code =Column(String, nullable=True)
#     storage = Column(String, nullable=True)
    






# # {
# #   "Reference_No": "REF001",
# #   "Samples": [
# #     {
# #       "Report_Id": 10,
# #       "Dimension": "Height",
# #       "Samples": [
# #          {"Sample_No":1, "Value": 10.02},
# #          {"Sample_No":2, "Value": 10.00},
# #          ...
# #          {"Sample_No":15, "Value": 9.99}
# #       ]
# #     },
# #     {
# #       "Report_Id": 11,
# #       "Dimension": "Width",
# #       "Samples": [
# #          {"Sample_No":1, "Value": 20.01},
# #          ...
# #       ]
# #     }
# #   ]
# # }



# # {
# #   "Reference_No": "REF001",

# #   "Common": {
# #      "Dimension_Parameter": "Mechanical Size",
# #      "Unit": "mm",
# #      "Remarks": "Overall good",
# #      "Marking_On_Material": "Laser-etched",
# #      "Visual_Inspection": "OK",
# #      "COC": "Provided",
# #      "Test_Reports": "Available",
# #      "Qty_Received": "100",
# #      "Qty_Inspected": "15",
# #      "Qty_Accepted": "15",
# #      "Inspection_Remarks": "All good"
# #   },

# #   "Dimensions": [
# #     {
# #       "Report_Id": 10,
# #       "Dimension_Name": "Height",
# #       "Basic_Dimension": 50.0,
# #       "Tolerance": 0.5,
# #       "Min": 49.5,
# #       "Max": 50.5,
# #       "Samples": [
# #         {"Sample_No": 1, "Value": 50.02, "Status": "OK"},
# #         {"Sample_No": 2, "Value": 49.98, "Status": "OK"},
# #         {"Sample_No": 3, "Value": 49.30, "Status": "NOT OK"}
# #       ]
# #     },

# #     {
# #       "Report_Id": 11,
# #       "Dimension_Name": "Width",
# #       "Basic_Dimension": 30.0,
# #       "Tolerance": 0.2,
# #       "Min": 29.8,
# #       "Max": 30.2,
# #       "Samples": [
# #         {"Sample_No": 1, "Value": 30.00, "Status": "OK"},
# #         {"Sample_No": 2, "Value": 30.10, "Status": "OK"}
# #       ]
# #     }
# #   ]
# # }







# #######################################   NPTRM  ###############################################


# # class PcbData(base):
# #     __tablename__ = "PcbData"
# #     ID = Column(Integer, Identity(start=1, increment=1), index=True)
# #     PCBserialNoPartNumber = Column(String, primary_key=True, index=True)

# #     serialNo = Column(String, index=True)
# #     partNumber = Column(String, index=True)

# #     productionOrder = Column(String)
# #     status = Column(String, default="New")
# #     quantity = Column(Integer, default=1)
# #     description = Column(String)

# #     userID = Column(String)
# #     userName = Column(String)
# #     userRole = Column(String)
# #     userSBU = Column(String)
# #     userSBUDIV = Column(String)
# #     Type = Column(String)

# #     createdAt = Column(DateTime(timezone=False), nullable=True)
# #     updatedAt = Column(DateTime(timezone=False), nullable=True)

# class PcbData(base):
#     __tablename__ = "PcbData"
#     ID = Column(Integer, Identity(start=1, increment=1), index=True)
#     PCBserialNoPartNumber = Column(String, primary_key=True, index=True)

#     serialNo = Column(String, index=True)
#     partNumber = Column(String, index=True)

#     productionOrder = Column(String)
#     status = Column(String, default="New")
#     quantity = Column(Integer, default=1)
#     description = Column(String)

#     userID = Column(String)
#     userName = Column(String)
#     userRole = Column(String)
#     userSBU = Column(String)
#     userSBUDIV = Column(String)
#     Type = Column(String)
#     plant = Column(String)
    
#     createdAt = Column(DateTime(timezone=False), nullable=True)
#     updatedAt = Column(DateTime(timezone=False), nullable=True)


# class ProcessFlowMaster(base):
#     __tablename__ = "process_flow_master"

#     flow_step_id = Column(Integer, primary_key=True, autoincrement=True)
#     step_order = Column(Integer, index=True)
#     step_name = Column(String, unique=True)
#     assignedToNameMRL = Column(String)
#     assignedToNameMRLExpiry = Column(String)
#     next_step_id = Column(Integer)

#     qualified_operators = relationship("OperatorStepMapping", back_populates="process_step")
#     equipment_to_stages = relationship("Equipments",back_populates="equipment_to_stage")
#     consumable_to_stages = relationship("Consumables",back_populates="consumable_to_stage")
#     qualified_stages = relationship("Processtype",back_populates="qualified_stages_batch")
    


# class OperatorStepMapping(base):
#     __tablename__ = "operator_step_mapping"
#     step_map_id = Column(Integer, primary_key=True, autoincrement=True)
#     flow_step_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
#     operator_staff_no = Column(String)
#     operator_name = Column(String)
#     operator_initial = Column(String)
#     operator_MRL = Column(String)
#     operator_MRL_Expiry= Column(String)

#     process_step = relationship("ProcessFlowMaster", back_populates="qualified_operators")
#     # eligibele_batch_series = relationship("Processtype", back_populates="qualified_operation")



# class PCBAssignment(base):
#     __tablename__ = "pcb_assignment"
#     assignment_id = Column(Integer, primary_key=True, autoincrement=True)
#     supervisor_staff_no = Column(String)
#     assigned_pcb_id = Column(String)
#     assignment_date = Column(String, default=lambda: datetime.utcnow().isoformat())
#     overall_status = Column(String, default="IN_PROGRESS")

#     # ⭐ NEW COLUMN (already exists in DB)
#     current_step_id = Column(Integer)


# class PCBProcessLog(base):
#     __tablename__ = "pcb_process_log"
#     log_id = Column(Integer, primary_key=True, autoincrement=True)
#     assignment_id = Column(Integer)
#     flow_step_id = Column(Integer)
#     assigned_operator_staff_no = Column(String)
#     process_status = Column(String, default="PENDING")
#     start_time = Column(String)
#     end_time = Column(String)


# class OperatorLog(base):
#     __tablename__="operator_log"
#     PCBserialNoPartNumber = Column(String,primary_key=True,index=True)
#     current_step_id = Column(Integer,primary_key=True,index=True)
#     assignment_id = Column(Integer)
#     Task_Status = Column(String)
#     Task_Name = Column(String)
#     operator_staff_no = Column(String)
#     log_Data = Column(JSON)
#     userID = Column(String)
#     operator_name = Column(String)
#     operator_initial = Column(String)
#     operator_MRL = Column(String)
#     operator_MRL_Expiry= Column(String)
#     userRole = Column(String)
#     userName = Column(String)
#     userSBU = Column(String)
#     userSBUDiv = Column(String)
#     start_time = Column(DateTime)
#     end_time = Column(DateTime)
#     file_name = Column(String, nullable=True)
#     file_path = Column(String, nullable=True)

# # class MRLRevalidationDocs(base):
# #     __tablename__ = "mrl_revalidation_docs"

# #     id = Column(Integer, primary_key=True, index=True)
# #     operatorid = Column(String)
# #     filename = Column(String)          # Physical filename on disk
# #     original_filename = Column(String) # Display filename
# #     file_path = Column(String)
# #     upload_date = Column(DateTime, default=datetime.now)


# # class MRLRevalidationDocsLog(base):
# #     __tablename__ = "mrl_revalidation_docs_logs"

# #     id = Column(Integer, primary_key=True, index=True)
# #     log_id = Column(Integer,ForeignKey("mrl_revalidation_docs.id"))
# #     operatorid = Column(String)
# #     action_type = Column(String)       # "UPLOAD", "DELETE", "REPLACE"
# #     # document_name = Column(String)
# #     file_name = Column(String)
# #     timestamp = Column(DateTime, default=datetime.now)    



# from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
# from datetime import datetime

# class MRLRevalidationDocs(base):
#     __tablename__ = "mrl_revalidation_docs"

#     id = Column(Integer, primary_key=True, index=True)
#     operatorid = Column(String)
#     userRole = Column(String)
#     userId = Column(String)
#     userName = Column(String)
#     userSBU = Column(String)
#     userSBUDiv = Column(String)
#     stage_id = Column(Integer)
#     filename = Column(String)
#     original_filename = Column(String)
#     file_path = Column(String)
#     upload_date = Column(DateTime, default=datetime.now)
#     # ADD THIS:
#     is_active = Column(Boolean, default=True) 

# class MRLRevalidationDocsLog(base):
#     __tablename__ = "mrl_revalidation_docs_logs"

#     id = Column(Integer, primary_key=True, index=True)
#     log_id = Column(Integer, ForeignKey("mrl_revalidation_docs.id"))
#     operatorid = Column(String)
#     userRole = Column(String)
#     userId = Column(String)
#     userName = Column(String)
#     userSBU = Column(String)
#     userSBUDiv = Column(String)
#     stage_id = Column(Integer)
#     action_type = Column(String) 
#     file_name = Column(String)
#     file_path = Column(String)
#     timestamp = Column(DateTime, default=datetime.now)




# # resouce planner


# class StageCapacityDB(base):
#     __tablename__ = "stage_capacity"

#     id = Column(Integer, primary_key=True, index=True)
#     name = Column(String, unique=True, index=True, nullable=False)
#     hours_per_shift = Column(Integer, default=0.0)
#     shifts_per_day = Column(Integer, default=0)
#     manufacturing_time_mins = Column(Float, default=0.0)

# class MonthlyDemandDB(base):
#     __tablename__ = "monthly_demand"

#     id = Column(Integer, primary_key=True, index=True)
#     year = Column(Integer, index=True, nullable=False)
#     month = Column(String, nullable=False)
#     hexa_target = Column(Integer, default=0)
#     octa_target = Column(Integer, default=0)
#     total_quantity  = Column(Integer,default = 0)
#     SMT_line_utilization = Column(Float,nullable=True)
#     Ionic_Contamination_utilization =Column(Float,nullable=True)
#     FPT_utilization= Column(Float,nullable=True)
#     Gap_welding_utilization = Column(Float,nullable=True)
#     ERSA_utilization = Column(Float,nullable=True)
#     Xray_utilization = Column(Float,nullable=True)
#     AOI_utilization = Column(Float,nullable=True)
#     Varnish_utilization = Column(Float,nullable=True)
#     Cleaning_utilization = Column(Float,nullable=True)
#     Visual_Inspection_utilization = Column(Float,nullable=True)
#     ATE_1_utilization = Column(Float,nullable=True)
#     ATE_2_utilization = Column(Float,nullable=True)
#     updated_time = Column(DateTime,nullable=True)








# """
# reowrk tables
# """



# class ReworkStages(base):
#     __tablename__ = "rework_stages"
#     # Configuration table to whitelist stages that can trigger rework
#     id = Column(Integer, primary_key=True)
#     stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
#     stage_name = Column(String)
#     dest_rework_stage_id = Column(Integer)

# # class ReworkTrack(base):
# #     __tablename__ = "rework_track"
# #     id = Column(Integer, primary_key=True, autoincrement=True)
    
# #     # Traceability Links
# #     PCBserialNoPartNumber = Column(String, ForeignKey("PcbData.PCBserialNoPartNumber"))
# #     assignment_id = Column(Integer, ForeignKey("pcb_assignment.assignment_id"))
    
# #     # The "Bookmark" for the return journey
# #     source_stage_id = Column(Integer) # The stage where defect was found
# #     rework_stage_id = Column(Integer) # Usually a fixed ID for the "Rework Station"
    
# #     remarks = Column(String) # Defect description
# #     is_resolved = Column(Boolean, default=False) # Your 'flag'
# #     created_at = Column(DateTime, default=datetime.utcnow) # time
# #     resolved_at = Column(DateTime, nullable=True)
# #     is_pcb_rejected =  Column(Boolean,default = False)
# #     resolved_remarks = Column(String,default = "")
# #     rework_raised_operator = Column(String,default = "")
# #     rework_completed_operator = Column(String,default = "")
# #     rework_started_operator = Column(String,default = "")




# # class Equipments(base):
# #     __tablename__="equipment_details"
# #     id = Column(Integer,primary_key=True)
# #     stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
# #     eqpt_no = Column(String)
# #     eqpt_name = Column(String)
# #     eqpt_make = Column(String)
# #     eqpt_model = Column(String)
# #     eqpt_due_date = Column(Date)
# #     image_path =Column(String)
# #     instruction_path = Column(String)
# #     equipment_to_stage = relationship("ProcessFlowMaster", back_populates="equipment_to_stages")
# #     is_euip_present = Column(Boolean, default=False)







# class Equipments(base):
#     __tablename__ = "equipment_details"
    
#     id = Column(Integer, primary_key=True)
#     stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
#     eqpt_no = Column(String)
#     eqpt_name = Column(String)
#     eqpt_make = Column(String)
#     eqpt_model = Column(String)
#     eqpt_due_date = Column(Date)
#     image_path = Column(String)
#     instruction_path = Column(String)
#     equipment_to_stage = relationship("ProcessFlowMaster", back_populates="equipment_to_stages")
#     is_euip_present = Column(Boolean, default=False)

#     # --- New Telemetry & Configuration Fields ---
#     machine_id = Column(String, index=True, nullable=False)
#     process_type = Column(String, nullable=False)
#     log_file = Column(String, nullable=True)
#     ip_address = Column(String, nullable=True)
#     power_on_codes = Column(String, nullable=True)
#     power_off_codes = Column(String, nullable=True)

# class Consumables(base):
#     __tablename__="consumables"
#     id = Column(Integer,primary_key=True)
#     stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
#     consumable_material_number = Column(String)
#     consumable_material_name = Column(String)
#     consumable_gr_number = Column(String)
#     consumable_year = Column(Date)
#     consumable_shelf_life = Column(Date)
#     batch_number = Column(String)
#     # image_path =Column(String)
#     # instruction_path = Column(String)
#     consumable_to_stage = relationship("ProcessFlowMaster", back_populates="consumable_to_stages")
#     is_consumable_present = Column(Boolean, default=False)
#     po_number = Column(Integer)
#     quantity = Column(Integer)

# class Processtype(base):
#     __tablename__ = "process_type"
#     id = Column(Integer, primary_key=True)
#     stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
#     process_type_batch= Column(Boolean)

#     qualified_stages_batch = relationship("ProcessFlowMaster", back_populates="qualified_stages")
#     # qualified_operation = relationship("OperatorStepMapping", back_populates="eligibele_batch_series")



# class ProgramDetails(base):
#     __tablename__ = "program_details"
#     id = Column(Integer, primary_key=True)
#     stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
#     program_name = Column(String)
#     is_program_present = Column(Boolean, default=False)


# class ProductTypeMaster(base):
#     __tablename__ = "product_type_master"
#     id = Column(Integer, primary_key=True)
#     product_type_name = Column(String)
#     sub_product_type_name = Column(String)
#     part_number = Column(String, unique=True, nullable=False)
#     description = Column(String,nullable=True)
#     plant_code = Column(String,ForeignKey("plants.plant_code"))

# class ProductWorkflowMapping(base):
#     __tablename__ = "product_workflow_mapping"
#     id = Column(Integer,Identity(start=1), primary_key=True)
#     product_type_id = Column(Integer)
#     product_part_number = Column(String(50), ForeignKey("product_type_master.part_number", ondelete="CASCADE"))
#     flow_step_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
#     step_sequence = Column(Integer) # The order: 1, 2, 3...
    


#     process_detail = relationship("ProcessFlowMaster")

# class Plant(base):
#     __tablename__ = "plants"

#     # plant_code is set as the Primary Key here
#     plant_code = Column(String, primary_key=True, index=True)
#     sbu = Column(String, nullable=False, unique=True)
#     company = Column(String, nullable=False)
#     location = Column(String, nullable=False)
#     is_active = Column(Boolean, default=True)


# class DynamicFormTemplate(base):
#     __tablename__ = "dynamic_form_templates"

#     id = Column(Integer, primary_key=True, index=True)
#     stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
    
#     # --- ADD THIS LINE ---
#     stage_name = Column(String, nullable=True) 
    
#     form_schema = Column(JSON) 
#     version = Column(Integer, default=1)
#     is_active = Column(Boolean, default=True)
#     created_by = Column(String, nullable=True)
#     updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
#     created_at = Column(DateTime, default=datetime.now)




# # CODE ADDED BY PRIYA FOR PHOTOSHOP
# from sqlalchemy import Column, Integer, String, Date, ForeignKey
# from sqlalchemy.orm import relationship
# # Ensure you are using the same 'Base' declarative base you use for your other models.

# class EventDB(base):
#     __tablename__ = "media_events"

#     id = Column(Integer, primary_key=True, index=True)
#     sbu_name = Column(String, index=True)
#     staff_no = Column(String)
#     event_name = Column(String)
#     execution_date = Column(Date)
    
#     # Relationship to link multiple images to this one event
#     images = relationship("EventImageDB", back_populates="event", cascade="all, delete-orphan")

# class EventImageDB(base):
#     __tablename__ = "media_event_images"

#     id = Column(Integer, primary_key=True, index=True)
#     event_id = Column(Integer, ForeignKey("media_events.id"))
#     file_name = Column(String)
#     file_path = Column(String) # The URL path to serve the image to React

#     event = relationship("EventDB", back_populates="images")

# class GalleryUser(base):
#     __tablename__ = "gallery_users"

#     id = Column(Integer, primary_key=True, index=True)
#     staff_name = Column(String, index=True)
#     staff_no = Column(String, unique=True, index=True)
#     company = Column(String)
#     sbu = Column(String)
#     sbu_division = Column(String)
#     is_admin = Column(Boolean, default=False)
#     password = Column(String) # For production, store HASHED passwords only!
#     role = Column(String, default="user") # e.g., "photographer" or "user" 

    
# from sqlalchemy import Column, Integer, String, Date, UniqueConstraint, extract
# # from sqlalchemy.orm import declarative_base

# # Base = declarative_base()

# class PublicHoliday(base):
#     __tablename__ = "public_holidays"
    
#     id = Column(Integer, primary_key=True, index=True)
#     holiday_date = Column(Date, unique=True, nullable=False)
#     name = Column(String, nullable=False) # e.g., "Republic Day", "Diwali"
    
#     # Optional: Storing year makes it faster to filter/delete an entire year's list
#     year = Column(Integer, nullable=False, index=True) 

# class MonthlyWorkingDays(base):
#     __tablename__ = "monthly_working_days"
    
#     id = Column(Integer, primary_key=True, index=True)
#     year = Column(Integer, nullable=False)
#     month = Column(Integer, nullable=False) # 1 to 12
#     total_working_days = Column(Float, nullable=False)
    
#     # Ensure we only have one record per year/month combination
#     __table_args__ = (UniqueConstraint('year', 'month', name='_year_month_uc'),)

# class CalendarException(base):
#     __tablename__ = "calendar_exceptions"
#     id = Column(Integer, primary_key=True, index=True)
#     exception_date = Column(Date, unique=True, nullable=False, index=True)
#     exception_type = Column(String, nullable=False)  # 'Working', 'Holiday', 'Half-Day'
#     note = Column(String)


# class Location(base):
#     __tablename__ ="location"
#     id=Column(Integer,primary_key=True,index=True)
#     location=Column(String, nullable=False)
#     part_number=Column(String,nullable=False)
#     product_part_number=Column(String(50), ForeignKey("product_type_master.part_number", ondelete="CASCADE"))


#     process_detail1 = relationship("ProductTypeMaster")

# class DefectCategory(base):
#     __tablename__="defect_category"
#     id=Column(Integer,primary_key=True,index=True)
#     defect_name=Column(String , nullable=False)
#     part_number=Column(String(50),ForeignKey("product_type_master.part_number"))

#     process_detail2 = relationship("ProductTypeMaster")


# #added by suraj for rework on 01_06_2026


# class ReworkFlowMaster(base):
#     __tablename__ = "rework_flow_master"
    
#     id = Column(Integer, primary_key=True, index=True, autoincrement=True)
#     flow_name = Column(String, unique=True, index=True, nullable=False)
#     last_destination_stage_id = Column(Integer, nullable=True)

    
#     # Relationship to fetch steps easily
#     steps = relationship("ReworkFlowMapping", back_populates="rework_flow", cascade="all, delete")

# class ReworkFlowMapping(base):
#     __tablename__ = "rework_flow_mapping"
    
#     id = Column(Integer, primary_key=True, index=True, autoincrement=True)
#     rework_flow_id = Column(Integer, ForeignKey("rework_flow_master.id", ondelete="CASCADE"))
#     flow_step_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id", ondelete="CASCADE"))
#     step_sequence = Column(Integer)
#     part_number = Column(String)
#     rework_flow = relationship("ReworkFlowMaster", back_populates="steps")
#     process = relationship("ProcessFlowMaster")





# # Links a Product to multiple configured Rework Flows
# class ProductReworkLink(base):
#     __tablename__ = "product_rework_link"
    
#     id = Column(Integer, primary_key=True, index=True, autoincrement=True)
#     part_number = Column(String(50), index=True)
#     rework_flow_id = Column(Integer, ForeignKey("rework_flow_master.id"))

# # Tracks the PCB while it's inside a specific rework subprocess
# class ReworkTrack(base):
#     __tablename__ = "rework_track"
    
#     id = Column(Integer, primary_key=True, index=True, autoincrement=True)
#     PCBserialNoPartNumber = Column(String, index=True)
#     assignment_id = Column(Integer, ForeignKey("pcb_assignment.assignment_id"))
#     source_stage_id = Column(Integer)
    
#     # Track WHICH subprocess the PCB is in, and WHERE it is within that subprocess
#     rework_flow_id = Column(Integer, ForeignKey("rework_flow_master.id")) 
#     current_step_sequence = Column(Integer, default=1) 
    
#     is_resolved = Column(Boolean, default=False)
#     raised_at = Column(DateTime, default=datetime.utcnow)
#     resolved_at = Column(DateTime, nullable=True)
#     raised_by_operator = Column(String, nullable=True)
#     remarks = Column(String, nullable=True)
#     is_pcb_rejected =  Column(Boolean,default = False)
#     resolved_remarks = Column(String,default = "")
#     rework_raised_operator = Column(String,default = "")
#     rework_completed_operator = Column(String,default = "")
#     rework_started_operator = Column(String,default = "")
#     defect_details = Column(JSON, nullable=True)
#     parent_rework_id = Column(Integer, ForeignKey("rework_track.id"), nullable=True)


    
# # class ReworkTrack(base):
# #     __tablename__ = "rework_track"
# #     id = Column(Integer, primary_key=True, autoincrement=True)
    
# #     # Traceability Links
# #     PCBserialNoPartNumber = Column(String, ForeignKey("PcbData.PCBserialNoPartNumber"))
# #     assignment_id = Column(Integer, ForeignKey("pcb_assignment.assignment_id"))
    
# #     # The "Bookmark" for the return journey
# #     source_stage_id = Column(Integer) # The stage where defect was found
# #     rework_stage_id = Column(Integer) # Usually a fixed ID for the "Rework Station"
    
# #     remarks = Column(String) # Defect description
# #     is_resolved = Column(Boolean, default=False) # Your 'flag'
# #     created_at = Column(DateTime, default=datetime.utcnow) # time
# #     resolved_at = Column(DateTime, nullable=True)
# #     is_pcb_rejected =  Column(Boolean,default = False)
# #     resolved_remarks = Column(String,default = "")
# #     rework_raised_operator = Column(String,default = "")
# #     rework_completed_operator = Column(String,default = "")
# #     rework_started_operator = Column(String,default = "")
# class ReworkProcessLog(base):
#     __tablename__ = "rework_process_log"
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     assignment_id = Column(Integer, ForeignKey("pcb_assignment.assignment_id"))
#     rework_flow_id = Column(Integer) # Links to the specific subprocess
#     flow_step_id = Column(Integer)   # The stage inside the subprocess
#     process_status = Column(String, default="PENDING")
#     start_time = Column(DateTime, nullable=True)
#     end_time = Column(DateTime, nullable=True)
#     assigned_operator_staff_no = Column(String, nullable=True)


# class PCBTraceability(base):
#     __tablename__ = "pcb_traceability"

#     id = Column(Integer, primary_key=True, autoincrement=True)

#     pcb_serial = Column(String, unique=True, index=True)
#     pcb_name = Column(String)

#     layout = Column(String)
#     assembly_batch = Column(String)

#     start_assembly = Column(String)
#     assembly_ready = Column(String)

#     spare_parts = Column(JSON)

#     created_at = Column(DateTime, default=datetime.utcnow)
#     updated_at = Column(
#         DateTime,
#         default=datetime.utcnow,
#         onupdate=datetime.utcnow
#     )




# class InventorySpares(base):
#     __tablename__ = "inventorty_spares"
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     flow_step_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
#     step_name=Column(String)
#     part_number=Column(String)
#     decription=Column(String)
#     qty_avl=Column(String)
#     threshold_qty=Column(String)
#     procurement_lead_time= Column(String)

# class ConsumablePartList(base):
#     __tablename__="consumable_part_list"
#     id= Column(Integer, primary_key=True, autoincrement=True)
#     flow_step_id=Column(Integer,ForeignKey("process_flow_master.flow_step_id"))
#     process_name=Column(String)
#     part_number=Column(String)
#     decription=Column(String)
   


#     process_detail = relationship("ProcessFlowMaster")

















from sqlalchemy import Column,Integer,String,Float,DateTime,ForeignKey,Date,LargeBinary,Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import date, datetime

from sqlalchemy import (
    create_engine, Column, Integer, String, ForeignKey,JSON, and_,
    select, DateTime, func, or_,Identity
)
base  = declarative_base()

# class UserProfile(base):
#     __tablename__ = "userProfiles"
#     userID = Column(String, primary_key=True)
#     username = Column(String)
#     userRole = Column(String)
#     admin = Column(String)
#     sbu = Column(String)
#     subdivision = Column(String)
#     description = Column(String)
#     company = Column(String)
#     password = Column(String)
#     createdAt = Column(DateTime(timezone=True))
#     updatedAt = Column(DateTime(timezone=True))

class QRRecord_db(base):
    __tablename__ = "qr_records"

    Reference_No= Column(String, primary_key = True, index=True)
    Timestamp = Column(DateTime)
    SL_No = Column(Integer, autoincrement=True) 
    BEL_Part_Number = Column(String)
    MPN= Column(String)
    Batch_Lot_No= Column(String)
    DateCode= Column(String)
    Quantity= Column(String)
    BEL_PO_No= Column(String)
    Vendor_Name= Column(String)
    OEM_Make= Column(String)
    Manufacturing_Place= Column(String)
    GR_No= Column(String)
    GR_Date= Column(DateTime)
    
    Description = Column(String)
    Vendor_Code = Column(String)
    Invoice_No  = Column(String)
    Invoice_Dt = Column(DateTime)

class LogBook_db(base):
    __tablename__ = "log_book"
    
    SL_No = Column(Integer, primary_key=True, autoincrement=True, index=True)
    Timestamp = Column(DateTime )
    BEL_Part_Number = Column(String )
    MPN = Column(String )
    Batch_Lot_No = Column(String )
    DateCode = Column(String )
    Quantity = Column(String )
    BEL_PO_No = Column(String )
    Vendor_Name = Column(String )
    OEM_Make = Column(String )
    Manufacturing_Place = Column(String)

class RoutingCard(base):
    __tablename__ = "Fab_RoutingCard"

    Id = Column(Integer, primary_key=True, index=True)
    Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
    BEL_PO_No = Column(Integer)  
    Vendor_Name = Column(String)
    Description = Column(String)  
    Record_Date = Column(String, default=datetime.now)       
    Quantity = Column(Integer)
    Invoice_No = Column(String)
    Invoice_Dt = Column(DateTime)
             
    No_of_Cases = Column(Integer)
    Location = Column(String)

    GR_No = Column(String)
    GR_Date = Column(DateTime)

class QRRecord_Generated(base):
    __tablename__ = "generated_qr_records"

    inspection_type = Column(String, nullable=True)

    Timestamp = Column(DateTime)
    SL_No = Column(Integer) 
    BEL_Part_Number = Column(String)
    MPN= Column(String)
    Batch_Lot_No= Column(String)
    DateCode= Column(String)
    Quantity= Column(String)
    BEL_PO_No= Column(String)
    Vendor_Name= Column(String)
    OEM_Make= Column(String)
    Manufacturing_Place= Column(String)
    GR_No= Column(String)
    GR_Date= Column(DateTime)
    Reference_No= Column(String, primary_key = True, index=True)
    Description = Column(String)
    Vendor_Code = Column(String)
    Invoice_No  = Column(String)
    Invoice_Dt = Column(DateTime)
    Status = Column(String)
    overall_status = Column(String,default="Generated")

    userID = Column(String)
    userName = Column(String)
    userRole = Column(String)
    userSBU = Column(String)
    userSBUDIV = Column(String)

    subcontracts = relationship("SubContract_Inspection", back_populates="qr_record", cascade="all, delete-orphan")
    dimensions = relationship("DimensionReport", back_populates="qr_record",cascade="all, delete-orphan")
    dimension_common_reports = relationship("DimensionCommonReport", back_populates="reference", cascade="all, delete-orphan")
    intender_report = relationship("Intender_Report", back_populates="qr_record",cascade="all, delete-orphan")
    Submission_Details = relationship("Authorized_Person", back_populates="qr_record",cascade="all, delete-orphan")
    instrument = relationship("Measuring_Instruments_Used", back_populates="qr_record",cascade="all, delete-orphan")

    
class DimensionInstrumentMap(base):
    __tablename__ = "dimension_instrument_map"

    Id = Column(Integer, primary_key=True, index=True)

    Report_Id = Column(Integer, ForeignKey("dimension_reports.Id"))
    Instrument_Id = Column(Integer, ForeignKey("measuring_instruments.Equipment_ID"))

    # Relationships
    report = relationship("DimensionReport", back_populates="instrument_links")
    instrument = relationship("Measuring_Instruments", back_populates="report_links")

class Measuring_Instruments(base):
    __tablename__ = "measuring_instruments"

    Description = Column(String)
    Equipment_ID = Column(Integer, primary_key=True, index=True)
    Measuring_Accuracy = Column(Float)
    Make_Model = Column(String)
    Cal_Date = Column(DateTime)
    Due_Date = Column(DateTime)

    report_links = relationship(
        "DimensionInstrumentMap",
        back_populates="instrument",
        cascade="all, delete-orphan"
    )
    instruments = relationship(
        "Measuring_Instruments_Used",
        back_populates="instrument_used",
        cascade="all, delete-orphan"
    )

class SubContract_Inspection(base):
    __tablename__ = "subcontract_inspection"

    SAN_NO = Column(Integer, primary_key=True, index=True)
    Control_No = Column(Integer)

    # Basic details (common in both tables)
    Part_No = Column(String)
    Description = Column(String)
    PO_NO = Column(String)
    Vendor_Name = Column(String)
    Quantity = Column(String)
    Sample = Column(String)
    Sale_Order = Column(String)
    Drg_Issue_Level = Column(Integer)

    Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
    Date = Column(Date, default=date.today)

    userID = Column(String)
    userName = Column(String)
    userRole = Column(String)
    userSBU = Column(String)
    userSBUDIV = Column(String)

    # Report section (only in second table)
    Vendor_Dimension_Report = Column(String, nullable=True)
    Visual_Inspection = Column(String, nullable=True)
    Raw_Material_Supplied = Column(String, nullable=True)
    Raw_Material_Test_Report = Column(String, nullable=True)
    # Relationship
    qr_record = relationship("QRRecord_Generated", back_populates="subcontracts")

# class Dimension_Report(base):
#     __tablename__ = "dimension_report"
#     id = Column(Integer,primary_key=True,index=True)
#     Basic_Dimension = Column(Float)
#     Measuring_Instr_Id = Column(Integer, ForeignKey("measuring_instruments.Id"))
#     Tolerance = Column(Float)
#     Min = Column(Float)
#     Max = Column(Float)
#     Sample_1 = Column(Float,nullable=True)
#     Sample_2 = Column(Float,nullable=True)
#     Sample_3 = Column(Float,nullable=True)
#     Sample_4 = Column(Float,nullable=True)
#     Sample_5 = Column(Float,nullable=True)
#     Sample_6= Column(Float,nullable=True)
#     Sample_7 = Column(Float,nullable=True)
#     Sample_8 = Column(Float,nullable=True)
#     Sample_9 = Column(Float,nullable=True)
#     Sample_10 = Column(Float,nullable=True)
#     Sample_11 = Column(Float,nullable=True)
#     Sample_12 = Column(Float,nullable=True)
#     Sample_13 = Column(Float,nullable=True)
#     Sample_14 = Column(Float,nullable=True)
#     Sample_15 = Column(Float,nullable=True)

#     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
#     qr_record = relationship("QRRecord_Generated", back_populates="dimensions")
#     measurement = relationship("Measuring_Instruments", back_populates="dimension")



class DimensionType(base):
    __tablename__ = "dimension_types"

    Id = Column(Integer, primary_key=True, index=True)
    Name = Column(String, nullable=False)

    reports = relationship("DimensionReport", back_populates="dimension_type")
    

# -------------------------------
# 2. Dimension Report (Per Dimension Per Reference_No)
# -------------------------------
class DimensionReport(base):
    __tablename__ = "dimension_reports"

    Id = Column(Integer, primary_key=True, index=True)
    Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
    Dimension_Type_Id = Column(Integer, ForeignKey("dimension_types.Id"))

    Basic_Dimension = Column(Float)
    Tolerance = Column(Float)
    Min = Column(Float)
    Max = Column(Float)
    dimension_type = relationship("DimensionType", back_populates="reports")
    qr_record = relationship("QRRecord_Generated", back_populates="dimensions")

    samples = relationship("DimensionSample", back_populates="report",
                           cascade="all, delete-orphan")
    instrument_links = relationship(
        "DimensionInstrumentMap",
        back_populates="report",
        cascade="all, delete-orphan"
    )

    
# -------------------------------
# 3. Dimension Samples (Values Entered by User)
# -------------------------------
class DimensionSample(base):
    __tablename__ = "dimension_samples"

    Id = Column(Integer, primary_key=True, index=True)
    Report_Id = Column(Integer, ForeignKey("dimension_reports.Id"))
    Sample_No = Column(Integer)  # 1 to 15
    Value = Column(Float)
    Status = Column(String)  # OK / NOT OK
    Remarks = Column(String,nullable=True)
    Dimension_View_Parameter = Column(String,nullable=True)
    Dimension_Parameter_Unit = Column(String)
    
    report = relationship("DimensionReport", back_populates="samples")


class DimensionCommonReport(base):
    __tablename__ = "dimension_common_report"

    Id = Column(Integer, primary_key=True, index=True)
    Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))


    
    Remarks = Column(String, nullable=True)

    Marking_On_Material = Column(String, nullable=True)
    Dimension_Remark = Column(String, nullable=True)
    Visual_Inspection_Report = Column(String, nullable=True)
    Electrical_Inspection_Remark = Column(String, nullable=True)
    Electrical_Parameter = Column(String, nullable=True)
    Functional = Column(String, nullable=True)
    Dimensions = Column(String, nullable=True)
    Visual_Inspection = Column(String, nullable=True)
    COC = Column(String, nullable=True)
    Test_Reports = Column(String, nullable=True)
    Imported_Doc_Received = Column(String, nullable=True)
    Malware_Free_Cert = Column(String, nullable=True)
    FOD_Check = Column(String, nullable=True)
    Counterfeit_Checked = Column(String, nullable=True)
    MFG_Date = Column(Date, nullable=True)
    Exp_Date = Column(Date, nullable=True)
    Qty_Received = Column(String, nullable=True)
    Qty_Inspected = Column(String, nullable=True)
    Qty_Accepted = Column(String, nullable=True)
    Qty_Rejected = Column(String, nullable=True)


    Inspection_Remarks = Column(String, nullable=True)

    userID = Column(String)
    userName = Column(String)
    userRole = Column(String)
    userSBU = Column(String)
    userSBUDIV = Column(String)

    # Links all DimensionReports for this reference
    reference = relationship("QRRecord_Generated", back_populates="dimension_common_reports")


class Intender_Report(base):
    __tablename__ = "intender_report"

    Id = Column(Integer, primary_key=True, index=True)
    Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
    Project_SaleOrder = Column(String)  # 1 to 15
    Result = Column(String)
    Serial_Numbers = Column(String)  # OK / NOT OK
    Remarks = Column(String)
    Date = Column(Date)
    Status = Column(String)

    userID = Column(String)
    userName = Column(String)
    userRole = Column(String)
    userSBU = Column(String)
    userSBUDIV = Column(String)
    
    qr_record = relationship("QRRecord_Generated", back_populates="intender_report")



class Authorized_Person(base):
    __tablename__ = 'user_data'
    
    id = Column(Integer, primary_key=True)
    Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"),nullable=False)

    insUserID = Column(String,nullable=False)
    insUserName = Column(String) 
    insUserRole = Column(String)
    insUserSBU = Column(String)
    insUserSBUDIV = Column(String)
    insDate = Column(Date,default=date.today)

    insfilename = Column(String)
    insmimetype = Column(String)
    insdata = Column(LargeBinary)

    insRemarks = Column(String)

    appUserID = Column(String,nullable=True)
    appUserName = Column(String,nullable=True)
    appUserRole = Column(String,nullable=True)
    appUserSBU = Column(String,nullable=True)
    appUserSBUDIV = Column(String,nullable=True)

    appfilename = Column(String,nullable=True)
    appmimetype = Column(String,nullable=True)
    appdata = Column(LargeBinary,nullable=True)

    appDate = Column(Date,nullable=True)
    appRemarks = Column(String,nullable=True)


    # Staff_No = Column(Integer) #userID
    # Name = Column(String)
    # Role = Column(String)
    # Date = Column(Date,default=date.today)


    qr_record = relationship("QRRecord_Generated", back_populates="Submission_Details")


# class Authorized_Person(base):
#     __tablename__ = 'user_data'
    
#     id = Column(Integer, primary_key=True)
#     Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"), nullable=False)

#     insUserID = Column(String, nullable=False)
#     insUserName = Column(String) 
#     insUserRole = Column(String)
#     insUserSBU = Column(String)
#     insUserSBUDIV = Column(String)
#     insDate = Column(Date, default=date.today)
#     insfilename = Column(String)
#     insmimetype = Column(String)
#     insdata = Column(LargeBinary)
#     insRemarks = Column(String)

#     appUserID = Column(String, nullable=True)
#     appUserName = Column(String, nullable=True)
#     appUserRole = Column(String, nullable=True)
#     appUserSBU = Column(String, nullable=True)
#     appUserSBUDIV = Column(String, nullable=True)

#     appfilename = Column(String, nullable=True)
#     appmimetype = Column(String, nullable=True)
#     appdata = Column(LargeBinary, nullable=True)

#     appDate = Column(Date, nullable=True) 
#     appRemarks = Column(String, nullable=True)
    




class Measuring_Instruments_Used(base):
    __tablename__ = "measuring_instrument_used"

    id = Column(Integer,primary_key=True)
    Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
    Equipment_ID = Column(Integer, ForeignKey("measuring_instruments.Equipment_ID"))

    qr_record = relationship("QRRecord_Generated", back_populates="instrument")
    instrument_used = relationship(
        "Measuring_Instruments",
        back_populates="instruments"
    )

class Indenter(base):
    __tablename__ = "indenter_table"

    indId = Column(Integer, primary_key=True)
    userID = Column(String, ForeignKey("userProfiles.userID"))
    # indUserID = Column(String)
    # indUserName = Column(String)
    # indUserRole = Column(String)
    # indUserSBU = Column(String)
    # indUserSBUDIV = Column(String)
    # indPhoneNo = Column(String)
    # date = Column(Date)
    user = relationship("UserProfile")

class IndenterApproval(base):
    __tablename__ = "indenter_approval_details"

    id = Column(Integer, primary_key=True)
    Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
    serialNo = Column(String)

    indUserID = Column(String)
    indUserName = Column(String)
    indUserRole = Column(String, default="Indentor")
    indUserSBU = Column(String)
    indUserSBUDIV = Column(String)
    indPhoneNo = Column(String)
    date = Column(Date)
    
    insUserID = Column(String)
    insUserName = Column(String)
    insUserRole = Column(String)
    insUserSBU = Column(String)
    insUserSBUDIV = Column(String)

    Status = Column(String)



class MaterialInspection(base):
    __tablename__ = "material_inspection"

    id = Column(Integer, primary_key=True)
    Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))

    Batch_Lot_No = Column(String)
    Description = Column(String)
    Revision_Level = Column(String)
    Valuation_Type = Column(String)
    Storage_Location = Column(String)
    SO_Number = Column(String)
    Project = Column(String)
    Plant = Column(String)
    PO_Number = Column(String)
    GR_Number = Column(String)
    GR_Date = Column(String)
    Vendor_Name = Column(String)
    Ins_start_date = Column(Date,nullable=True)
    Ins_end_date = Column(Date,nullable=True)
    Test_eq_text = Column(String)
    Ins_Lot_Status = Column(String)

            # Control_No=next_control,
            # SAN_NO=next_san,
            # Part_No=qr.BEL_Part_Number,
            # Description=qr.Description,
            # PO_NO=qr.BEL_PO_No, - present
            # Vendor_Name=qr.Vendor_Name,- present
            # Quantity=qr.Quantity,
            # Sample="5 Nos",
            # Sale_Order="SO-1234", - present
            # Drg_Issue_Level=1, 
            # Reference_No=qr.Reference_No, - present
            # Date=date.today() - present
    
    insUserID = Column(String)
    insUserName = Column(String)
    insUserRole = Column(String)
    insUserSBU = Column(String)
    insUserSBUDIV = Column(String)

class MaterialTables(base):
    __tablename__ = "material_table"

    id = Column(Integer,primary_key=True)
    Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))
    
    Type = Column(String)
    MIC_No = Column(Integer, nullable=True)	
    MIC	= Column(String, nullable=True)
    MIC_Desc = Column(String, nullable=True)
    Sampling_Procedure = Column(String, nullable=True)
    Sampling_Qty = Column(String, nullable=True)	
    Inspected_Qty = Column(String, nullable=True)
    UoM	= Column(String, nullable=True)
    TargetValue	= Column(String, nullable=True)
    LowerLimit = Column(String, nullable=True)
    UpperLimit	= Column(String, nullable=True)
    SampleNo = Column(Integer, nullable=True)	
    Result = Column(String, nullable=True)
    Valuation = Column(String, nullable=True)
    InspDate = Column(Date, nullable=True)
    Remarks = Column(String, nullable=True)


class MaterialSummary(base):
    __tablename__ = "materialsummary"

    id = Column(Integer,primary_key=True)
    Reference_No = Column(String, ForeignKey("generated_qr_records.Reference_No"))

    qty_blocked = Column(Integer, nullable=True)
    qty_returned = Column(Integer, nullable=True)
    UD_Code =Column(String, nullable=True)
    storage = Column(String, nullable=True)
    






# {
#   "Reference_No": "REF001",
#   "Samples": [
#     {
#       "Report_Id": 10,
#       "Dimension": "Height",
#       "Samples": [
#          {"Sample_No":1, "Value": 10.02},
#          {"Sample_No":2, "Value": 10.00},
#          ...
#          {"Sample_No":15, "Value": 9.99}
#       ]
#     },
#     {
#       "Report_Id": 11,
#       "Dimension": "Width",
#       "Samples": [
#          {"Sample_No":1, "Value": 20.01},
#          ...
#       ]
#     }
#   ]
# }



# {
#   "Reference_No": "REF001",

#   "Common": {
#      "Dimension_Parameter": "Mechanical Size",
#      "Unit": "mm",
#      "Remarks": "Overall good",
#      "Marking_On_Material": "Laser-etched",
#      "Visual_Inspection": "OK",
#      "COC": "Provided",
#      "Test_Reports": "Available",
#      "Qty_Received": "100",
#      "Qty_Inspected": "15",
#      "Qty_Accepted": "15",
#      "Inspection_Remarks": "All good"
#   },

#   "Dimensions": [
#     {
#       "Report_Id": 10,
#       "Dimension_Name": "Height",
#       "Basic_Dimension": 50.0,
#       "Tolerance": 0.5,
#       "Min": 49.5,
#       "Max": 50.5,
#       "Samples": [
#         {"Sample_No": 1, "Value": 50.02, "Status": "OK"},
#         {"Sample_No": 2, "Value": 49.98, "Status": "OK"},
#         {"Sample_No": 3, "Value": 49.30, "Status": "NOT OK"}
#       ]
#     },

#     {
#       "Report_Id": 11,
#       "Dimension_Name": "Width",
#       "Basic_Dimension": 30.0,
#       "Tolerance": 0.2,
#       "Min": 29.8,
#       "Max": 30.2,
#       "Samples": [
#         {"Sample_No": 1, "Value": 30.00, "Status": "OK"},
#         {"Sample_No": 2, "Value": 30.10, "Status": "OK"}
#       ]
#     }
#   ]
# }







#######################################   NPTRM  ###############################################


# class PcbData(base):
#     __tablename__ = "PcbData"
#     ID = Column(Integer, Identity(start=1, increment=1), index=True)
#     PCBserialNoPartNumber = Column(String, primary_key=True, index=True)

#     serialNo = Column(String, index=True)
#     partNumber = Column(String, index=True)

#     productionOrder = Column(String)
#     status = Column(String, default="New")
#     quantity = Column(Integer, default=1)
#     description = Column(String)

#     userID = Column(String)
#     userName = Column(String)
#     userRole = Column(String)
#     userSBU = Column(String)
#     userSBUDIV = Column(String)
#     Type = Column(String)

#     createdAt = Column(DateTime(timezone=False), nullable=True)
#     updatedAt = Column(DateTime(timezone=False), nullable=True)

class PcbData(base):
    __tablename__ = "PcbData"
    ID = Column(Integer, Identity(start=1, increment=1), index=True)
    PCBserialNoPartNumber = Column(String, primary_key=True, index=True)

    serialNo = Column(String, index=True)
    partNumber = Column(String, index=True)

    productionOrder = Column(String)
    status = Column(String, default="New")
    quantity = Column(Integer, default=1)
    description = Column(String)

    userID = Column(String)
    userName = Column(String)
    userRole = Column(String)
    userSBU = Column(String)
    userSBUDIV = Column(String)
    Type = Column(String)
    plant = Column(String)
    
    createdAt = Column(DateTime(timezone=False), nullable=True)
    updatedAt = Column(DateTime(timezone=False), nullable=True)


class ProcessFlowMaster(base):
    __tablename__ = "process_flow_master"

    flow_step_id = Column(Integer, primary_key=True, autoincrement=True)
    step_order = Column(Integer, index=True)
    step_name = Column(String, unique=True)
    assignedToNameMRL = Column(String)
    assignedToNameMRLExpiry = Column(String)
    next_step_id = Column(Integer)
    plant_code = Column(String)
    

    qualified_operators = relationship("OperatorStepMapping", back_populates="process_step")
    equipment_to_stages = relationship("Equipments",back_populates="equipment_to_stage")
    consumable_to_stages = relationship("Consumables",back_populates="consumable_to_stage")
    qualified_stages = relationship("Processtype",back_populates="qualified_stages_batch")
    


class OperatorStepMapping(base):
    __tablename__ = "operator_step_mapping"
    step_map_id = Column(Integer, primary_key=True, autoincrement=True)
    flow_step_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
    operator_staff_no = Column(String)
    operator_name = Column(String)
    operator_initial = Column(String)
    operator_MRL = Column(String)
    operator_MRL_Expiry= Column(String)

    process_step = relationship("ProcessFlowMaster", back_populates="qualified_operators")
    # eligibele_batch_series = relationship("Processtype", back_populates="qualified_operation")



class PCBAssignment(base):
    __tablename__ = "pcb_assignment"
    assignment_id = Column(Integer, primary_key=True, autoincrement=True)
    supervisor_staff_no = Column(String)
    assigned_pcb_id = Column(String)
    assignment_date = Column(String, default=lambda: datetime.utcnow().isoformat())
    overall_status = Column(String, default="IN_PROGRESS")

    # ⭐ NEW COLUMN (already exists in DB)
    current_step_id = Column(Integer)


class PCBProcessLog(base):
    __tablename__ = "pcb_process_log"
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    assignment_id = Column(Integer)
    flow_step_id = Column(Integer)
    assigned_operator_staff_no = Column(String)
    process_status = Column(String, default="PENDING")
    start_time = Column(String)
    end_time = Column(String)


class OperatorLog(base):
    __tablename__="operator_log"
    PCBserialNoPartNumber = Column(String,primary_key=True,index=True)
    current_step_id = Column(Integer,primary_key=True,index=True)
    assignment_id = Column(Integer)
    Task_Status = Column(String)
    Task_Name = Column(String)
    operator_staff_no = Column(String)
    log_Data = Column(JSON)
    userID = Column(String)
    operator_name = Column(String)
    operator_initial = Column(String)
    operator_MRL = Column(String)
    operator_MRL_Expiry= Column(String)
    userRole = Column(String)
    userName = Column(String)
    userSBU = Column(String)
    userSBUDiv = Column(String)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    file_name = Column(String, nullable=True)
    file_path = Column(String, nullable=True)

# class MRLRevalidationDocs(base):
#     __tablename__ = "mrl_revalidation_docs"

#     id = Column(Integer, primary_key=True, index=True)
#     operatorid = Column(String)
#     filename = Column(String)          # Physical filename on disk
#     original_filename = Column(String) # Display filename
#     file_path = Column(String)
#     upload_date = Column(DateTime, default=datetime.now)


# class MRLRevalidationDocsLog(base):
#     __tablename__ = "mrl_revalidation_docs_logs"

#     id = Column(Integer, primary_key=True, index=True)
#     log_id = Column(Integer,ForeignKey("mrl_revalidation_docs.id"))
#     operatorid = Column(String)
#     action_type = Column(String)       # "UPLOAD", "DELETE", "REPLACE"
#     # document_name = Column(String)
#     file_name = Column(String)
#     timestamp = Column(DateTime, default=datetime.now)    



from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from datetime import datetime

class MRLRevalidationDocs(base):
    __tablename__ = "mrl_revalidation_docs"

    id = Column(Integer, primary_key=True, index=True)
    operatorid = Column(String)
    userRole = Column(String)
    userId = Column(String)
    userName = Column(String)
    userSBU = Column(String)
    userSBUDiv = Column(String)
    stage_id = Column(Integer)
    filename = Column(String)
    original_filename = Column(String)
    file_path = Column(String)
    upload_date = Column(DateTime, default=datetime.now)
    # ADD THIS:
    is_active = Column(Boolean, default=True) 

class MRLRevalidationDocsLog(base):
    __tablename__ = "mrl_revalidation_docs_logs"

    id = Column(Integer, primary_key=True, index=True)
    log_id = Column(Integer, ForeignKey("mrl_revalidation_docs.id"))
    operatorid = Column(String)
    userRole = Column(String)
    userId = Column(String)
    userName = Column(String)
    userSBU = Column(String)
    userSBUDiv = Column(String)
    stage_id = Column(Integer)
    action_type = Column(String) 
    file_name = Column(String)
    file_path = Column(String)
    timestamp = Column(DateTime, default=datetime.now)




# resouce planner


class StageCapacityDB(base):
    __tablename__ = "stage_capacity"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    hours_per_shift = Column(Integer, default=0.0)
    shifts_per_day = Column(Integer, default=0)
    manufacturing_time_mins = Column(Float, default=0.0)

# class MonthlyDemandDB(base):
#     __tablename__ = "monthly_demand"

#     id = Column(Integer, primary_key=True, index=True)
#     year = Column(Integer, index=True, nullable=False)
#     month = Column(String, nullable=False)
#     hexa_target = Column(Integer, default=0)
#     octa_target = Column(Integer, default=0)
#     total_quantity  = Column(Integer,default = 0)
#     SMT_line_utilization = Column(Float,nullable=True)
#     Ionic_Contamination_utilization =Column(Float,nullable=True)
#     FPT_utilization= Column(Float,nullable=True)
#     Gap_welding_utilization = Column(Float,nullable=True)
#     ERSA_utilization = Column(Float,nullable=True)
#     Xray_utilization = Column(Float,nullable=True)
#     AOI_utilization = Column(Float,nullable=True)
#     Varnish_utilization = Column(Float,nullable=True)
#     Cleaning_utilization = Column(Float,nullable=True)
#     Visual_Inspection_utilization = Column(Float,nullable=True)
#     ATE_1_utilization = Column(Float,nullable=True)
#     ATE_2_utilization = Column(Float,nullable=True)
#     updated_time = Column(DateTime,nullable=True)
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from datetime import datetime

class MonthlyDemandDB(base):
    __tablename__ = "monthly_demand"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, index=True, nullable=False)
    month = Column(String, nullable=False)
    
    # NEW: Dynamic JSON column to hold all part numbers and their targets
    product_target = Column(JSON, default={})

    total_quantity  = Column(Integer, default=0)
    SMT_line_utilization = Column(Float, nullable=True)
    Ionic_Contamination_utilization = Column(Float, nullable=True)
    FPT_utilization = Column(Float, nullable=True)
    Gap_welding_utilization = Column(Float, nullable=True)
    ERSA_utilization = Column(Float, nullable=True)
    Xray_utilization = Column(Float, nullable=True)
    AOI_utilization = Column(Float, nullable=True)
    Varnish_utilization = Column(Float, nullable=True)
    Cleaning_utilization = Column(Float, nullable=True)
    Visual_Inspection_utilization = Column(Float, nullable=True)
    ATE_1_utilization = Column(Float, nullable=True)
    ATE_2_utilization = Column(Float, nullable=True)
    updated_time = Column(DateTime, nullable=True)








"""
reowrk tables
"""



class ReworkStages(base):
    __tablename__ = "rework_stages"
    # Configuration table to whitelist stages that can trigger rework
    id = Column(Integer, primary_key=True)
    stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
    stage_name = Column(String)
    dest_rework_stage_id = Column(Integer)

# class ReworkTrack(base):
#     __tablename__ = "rework_track"
#     id = Column(Integer, primary_key=True, autoincrement=True)
    
#     # Traceability Links
#     PCBserialNoPartNumber = Column(String, ForeignKey("PcbData.PCBserialNoPartNumber"))
#     assignment_id = Column(Integer, ForeignKey("pcb_assignment.assignment_id"))
    
#     # The "Bookmark" for the return journey
#     source_stage_id = Column(Integer) # The stage where defect was found
#     rework_stage_id = Column(Integer) # Usually a fixed ID for the "Rework Station"
    
#     remarks = Column(String) # Defect description
#     is_resolved = Column(Boolean, default=False) # Your 'flag'
#     created_at = Column(DateTime, default=datetime.utcnow) # time
#     resolved_at = Column(DateTime, nullable=True)
#     is_pcb_rejected =  Column(Boolean,default = False)
#     resolved_remarks = Column(String,default = "")
#     rework_raised_operator = Column(String,default = "")
#     rework_completed_operator = Column(String,default = "")
#     rework_started_operator = Column(String,default = "")




# class Equipments(base):
#     __tablename__="equipment_details"
#     id = Column(Integer,primary_key=True)
#     stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
#     eqpt_no = Column(String)
#     eqpt_name = Column(String)
#     eqpt_make = Column(String)
#     eqpt_model = Column(String)
#     eqpt_due_date = Column(Date)
#     image_path =Column(String)
#     instruction_path = Column(String)
#     equipment_to_stage = relationship("ProcessFlowMaster", back_populates="equipment_to_stages")
#     is_euip_present = Column(Boolean, default=False)







class Equipments(base):
    __tablename__ = "equipment_details"
    
    id = Column(Integer, primary_key=True)
    stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
    eqpt_no = Column(String)
    eqpt_name = Column(String)
    eqpt_make = Column(String)
    eqpt_model = Column(String)
    eqpt_due_date = Column(Date)
    image_path = Column(String)
    instruction_path = Column(String)
    equipment_to_stage = relationship("ProcessFlowMaster", back_populates="equipment_to_stages")
    is_euip_present = Column(Boolean, default=False)

    # --- New Telemetry & Configuration Fields ---
    machine_id = Column(String, index=True, nullable=False)
    process_type = Column(String, nullable=False)
    log_file = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    power_on_codes = Column(String, nullable=True)
    power_off_codes = Column(String, nullable=True)
    workcenter_name = Column(String, nullable=True)
    plant_code = Column(String)

class Consumables(base):
    __tablename__="consumables"
    id = Column(Integer,primary_key=True)
    stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
    consumable_material_number = Column(String)
    consumable_material_name = Column(String)
    consumable_gr_number = Column(String)
    consumable_year = Column(Date)
    consumable_shelf_life = Column(Date)
    batch_number = Column(String)
    threshold_qty = Column(String)
    # image_path =Column(String)
    # instruction_path = Column(String)
    consumable_to_stage = relationship("ProcessFlowMaster", back_populates="consumable_to_stages")
    is_consumable_present = Column(Boolean, default=False)
    po_number = Column(Integer)
    quantity = Column(Integer)

class Processtype(base):
    __tablename__ = "process_type"
    id = Column(Integer, primary_key=True)
    stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
    process_type_batch= Column(Boolean)

    qualified_stages_batch = relationship("ProcessFlowMaster", back_populates="qualified_stages")
    # qualified_operation = relationship("OperatorStepMapping", back_populates="eligibele_batch_series")



class ProgramDetails(base):
    __tablename__ = "program_details"
    id = Column(Integer, primary_key=True)
    stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
    program_name = Column(String)
    is_program_present = Column(Boolean, default=False)


class ProductTypeMaster(base):
    __tablename__ = "product_type_master"
    id = Column(Integer, primary_key=True)
    product_type_name = Column(String)
    sub_product_type_name = Column(String)
    part_number = Column(String, unique=True, nullable=False)
    description = Column(String,nullable=True)
    plant_code = Column(String,ForeignKey("plants.plant_code"))

class ProductWorkflowMapping(base):
    __tablename__ = "product_workflow_mapping"
    id = Column(Integer,Identity(start=1), primary_key=True)
    product_type_id = Column(Integer)
    product_part_number = Column(String(50), ForeignKey("product_type_master.part_number", ondelete="CASCADE"))
    flow_step_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
    step_sequence = Column(Integer) # The order: 1, 2, 3...
    # --- Added Process Time Columns ---
    process_time = Column(String, nullable=True)          # Stores string e.g. "01:30:00"
    process_time_seconds = Column(Integer, nullable=True) # Stores total seconds e.g. 5400 for analytics


    process_detail = relationship("ProcessFlowMaster")

# class Plant(base):
#     __tablename__ = "plants"

#     # plant_code is set as the Primary Key here
#     plant_code = Column(String, primary_key=True, index=True)
#     sbu = Column(String, nullable=False, unique=True)
#     company = Column(String, nullable=False)
#     location = Column(String, nullable=False)
#     is_active = Column(Boolean, default=True)

class Plant(base):
    __tablename__ = "plants"

    plant_code = Column(String, primary_key=True, index=True)  # Werks (Plant Code)
    sbu = Column(String, nullable=False, unique=True)          # Gsber / Gtext (SBU Code & Desc)
    company = Column(String, nullable=False)                   # Bukrs / Butxt (Company Code & Desc)
    location = Column(String, nullable=False)                  # Name2 (Plant Code Desc)
    is_active = Column(Boolean, default=True)


class DynamicFormTemplate(base):
    __tablename__ = "dynamic_form_templates"

    id = Column(Integer, primary_key=True, index=True)
    stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
    
    # --- ADD THIS LINE ---
    stage_name = Column(String, nullable=True) 
    
    form_schema = Column(JSON) 
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_by = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    created_at = Column(DateTime, default=datetime.now)




# CODE ADDED BY PRIYA FOR PHOTOSHOP
from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
# Ensure you are using the same 'Base' declarative base you use for your other models.

class EventDB(base):
    __tablename__ = "media_events"

    id = Column(Integer, primary_key=True, index=True)
    sbu_name = Column(String, index=True)
    staff_no = Column(String)
    event_name = Column(String)
    execution_date = Column(Date)
    
    # Relationship to link multiple images to this one event
    images = relationship("EventImageDB", back_populates="event", cascade="all, delete-orphan")

class EventImageDB(base):
    __tablename__ = "media_event_images"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("media_events.id"))
    file_name = Column(String)
    file_path = Column(String) # The URL path to serve the image to React

    event = relationship("EventDB", back_populates="images")

class GalleryUser(base):
    __tablename__ = "gallery_users"

    id = Column(Integer, primary_key=True, index=True)
    staff_name = Column(String, index=True)
    staff_no = Column(String, unique=True, index=True)
    company = Column(String)
    sbu = Column(String)
    sbu_division = Column(String)
    is_admin = Column(Boolean, default=False)
    password = Column(String) # For production, store HASHED passwords only!
    role = Column(String, default="user") # e.g., "photographer" or "user" 

    
from sqlalchemy import Column, Integer, String, Date, UniqueConstraint, extract
# from sqlalchemy.orm import declarative_base

# Base = declarative_base()

class PublicHoliday(base):
    __tablename__ = "public_holidays"
    
    id = Column(Integer, primary_key=True, index=True)
    holiday_date = Column(Date, unique=True, nullable=False)
    name = Column(String, nullable=False) # e.g., "Republic Day", "Diwali"
    
    # Optional: Storing year makes it faster to filter/delete an entire year's list
    year = Column(Integer, nullable=False, index=True) 

class MonthlyWorkingDays(base):
    __tablename__ = "monthly_working_days"
    
    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False) # 1 to 12
    total_working_days = Column(Float, nullable=False)
    
    # Ensure we only have one record per year/month combination
    __table_args__ = (UniqueConstraint('year', 'month', name='_year_month_uc'),)

class CalendarException(base):
    __tablename__ = "calendar_exceptions"
    id = Column(Integer, primary_key=True, index=True)
    exception_date = Column(Date, unique=True, nullable=False, index=True)
    exception_type = Column(String, nullable=False)  # 'Working', 'Holiday', 'Half-Day'
    note = Column(String)


class Location(base):
    __tablename__ ="location"
    id=Column(Integer,primary_key=True,index=True)
    location=Column(String, nullable=False)
    part_number=Column(String,nullable=False)
    product_part_number=Column(String(50), ForeignKey("product_type_master.part_number", ondelete="CASCADE"))


    process_detail1 = relationship("ProductTypeMaster")

class DefectCategory(base):
    __tablename__="defect_category"
    id=Column(Integer,primary_key=True,index=True)
    defect_name=Column(String , nullable=False)
    part_number=Column(String(50),ForeignKey("product_type_master.part_number"))

    process_detail2 = relationship("ProductTypeMaster")


#added by suraj for rework on 01_06_2026


class ReworkFlowMaster(base):
    __tablename__ = "rework_flow_master"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    flow_name = Column(String, unique=True, index=True, nullable=False)
    last_destination_stage_id = Column(Integer, nullable=True)

    
    # Relationship to fetch steps easily
    steps = relationship("ReworkFlowMapping", back_populates="rework_flow", cascade="all, delete")

class ReworkFlowMapping(base):
    __tablename__ = "rework_flow_mapping"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    rework_flow_id = Column(Integer, ForeignKey("rework_flow_master.id", ondelete="CASCADE"))
    flow_step_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id", ondelete="CASCADE"))
    step_sequence = Column(Integer)
    part_number = Column(String)
    rework_flow = relationship("ReworkFlowMaster", back_populates="steps")
    process = relationship("ProcessFlowMaster")





# Links a Product to multiple configured Rework Flows
class ProductReworkLink(base):
    __tablename__ = "product_rework_link"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    part_number = Column(String(50), index=True)
    rework_flow_id = Column(Integer, ForeignKey("rework_flow_master.id"))

# Tracks the PCB while it's inside a specific rework subprocess
class ReworkTrack(base):
    __tablename__ = "rework_track"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    PCBserialNoPartNumber = Column(String, index=True)
    assignment_id = Column(Integer, ForeignKey("pcb_assignment.assignment_id"))
    source_stage_id = Column(Integer)
    
    # Track WHICH subprocess the PCB is in, and WHERE it is within that subprocess
    rework_flow_id = Column(Integer, ForeignKey("rework_flow_master.id")) 
    current_step_sequence = Column(Integer, default=1) 
    
    is_resolved = Column(Boolean, default=False)
    raised_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    raised_by_operator = Column(String, nullable=True)
    remarks = Column(String, nullable=True)
    is_pcb_rejected =  Column(Boolean,default = False)
    resolved_remarks = Column(String,default = "")
    rework_raised_operator = Column(String,default = "")
    rework_completed_operator = Column(String,default = "")
    rework_started_operator = Column(String,default = "")
    defect_details = Column(JSON, nullable=True)
    parent_rework_id = Column(Integer, ForeignKey("rework_track.id"), nullable=True)


    

class ReworkProcessLog(base):
    __tablename__ = "rework_process_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    assignment_id = Column(Integer, ForeignKey("pcb_assignment.assignment_id"))
    rework_flow_id = Column(Integer) # Links to the specific subprocess
    flow_step_id = Column(Integer)   # The stage inside the subprocess
    process_status = Column(String, default="PENDING")
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    assigned_operator_staff_no = Column(String, nullable=True)


class PCBTraceability(base):
    __tablename__ = "pcb_traceability"

    id = Column(Integer, primary_key=True, autoincrement=True)

    pcb_serial = Column(String, unique=True, index=True)
    pcb_name = Column(String)

    layout = Column(String)
    assembly_batch = Column(String)

    start_assembly = Column(String)
    assembly_ready = Column(String)

    spare_parts = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )




class ConsumablePartList(base):
    __tablename__="consumable_part_list"
    id= Column(Integer, primary_key=True, autoincrement=True)
    flow_step_id=Column(Integer,ForeignKey("process_flow_master.flow_step_id"))
    process_name=Column(String)
    part_number=Column(String)
    decription=Column(String)
   


    process_detail = relationship("ProcessFlowMaster")


class BOMItem(base):
    __tablename__ = "bom_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Update "products.part_number" to match the actual tablename and column of your parent table
    product_part_number = Column(String, ForeignKey("product_type_master.part_number"), index=True)

    # Columns mapped from the BOM Excel files
    bom_item_no = Column(Integer)  # Maps to 'BOM item'
    material = Column(String, index=True)  # Maps to 'Material'
    material_description = Column(String)  # Maps to 'Material Description'
    base_uom = Column(String)  # Maps to 'Base Unit of Measure' (e.g., NO, G, L, KG)
    quantity_per_pcb = Column(Float)  # Maps to 'Quantity/PCB'
    storage_location = Column(String, nullable=True)  # Maps to 'Storage Location'
    plant = Column(String)  # Maps to 'Plant'


# class ReworkTrack(base):
#     __tablename__ = "rework_track"
#     id = Column(Integer, primary_key=True, autoincrement=True)
    
#     # Traceability Links
#     PCBserialNoPartNumber = Column(String, ForeignKey("PcbData.PCBserialNoPartNumber"))
#     assignment_id = Column(Integer, ForeignKey("pcb_assignment.assignment_id"))
    
#     # The "Bookmark" for the return journey
#     source_stage_id = Column(Integer) # The stage where defect was found
#     rework_stage_id = Column(Integer) # Usually a fixed ID for the "Rework Station"
    
#     remarks = Column(String) # Defect description
#     is_resolved = Column(Boolean, default=False) # Your 'flag'
#     created_at = Column(DateTime, default=datetime.utcnow) # time
#     resolved_at = Column(DateTime, nullable=True)
#     is_pcb_rejected =  Column(Boolean,default = False)
#     resolved_remarks = Column(String,default = "")
#     rework_raised_operator = Column(String,default = "")
#     rework_completed_operator = Column(String,default = "")
#     rework_started_operator = Column(String,default = "")



# class InventorySpares(base):
#     __tablename__ = "inventorty_spares"
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     flow_step_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
#     step_name=Column(String)
#     part_number=Column(String)
#     decription=Column(String)
#     qty_avl=Column(String)
#     threshold_qty=Column(String)
#     procurement_lead_time= Column(String)
#     eqpt_no = Column(String)





class InventorySpares(base):
    __tablename__ = "inventorty_spares"
    id = Column(Integer, primary_key=True, autoincrement=True)
    flow_step_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
    step_name=Column(String)
    part_number=Column(String)
    decription=Column(String)
    qty_avl=Column(String)
    threshold_qty=Column(String)
    procurement_lead_time= Column(String)
    eqpt_no = Column(String )
    sparetype= Column(String )



    # machine_no = relationship("Equipments")


    
class SPCConfiguration(base):
    __tablename__ = "spc_configuration"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
    machine_id = Column(String, index=True) # Linked to equipment
    
    # Tolerances
    maxTolerance = Column(Float, default=0.0)
    minTolerance = Column(Float, default=0.0)
    target = Column(Float, default=0.0)
    
    # Constants
    N = Column(Integer, default=3)
    A3 = Column(Float, default=1.954)
    B3 = Column(Float, default=0.0)
    B4= Column(Float, default=2.568)
    
    # Manual Baseline
    average = Column(Float, nullable=True)
    stdTPE = Column(Float, nullable=True)

class SPCDataLog(base):
    __tablename__ = "spc_data_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"))
    machine_id = Column(String, index=True)
    referral_number = Column(String, index=True)
    date = Column(Date)
    spc_values = Column(JSON) # Stores {"spc_1": 10.5, "spc_2": 10.6, ...}
    operator_id = Column(String)




class StepDocument(base):
    __tablename__ = "step_documents"
    id = Column(Integer, primary_key=True, index=True)
    step_name = Column(String, index=True) 
    filename = Column(String)
    file_path = Column(String)
    document_no = Column(String)


class MachineBreakdownLog(base):
    __tablename__ = "machine_breakdown_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    machine_id = Column(String, index=True)
    machine_name = Column(String)
    stage = Column(String, nullable=True)
    event_type = Column(String, nullable=True)
    downtime_hours = Column(Float, nullable=True, default=0.0) # Calculated duration
    breakdown_date = Column(String)
    breakdown_time = Column(String)
    issue_description = Column(String)
    reported_by = Column(String)
    resolution_remarks = Column(String, nullable=True)
    consumables_used = Column(String, default="no")
    spare_part_no = Column(String, nullable=True)
    spare_description = Column(String, nullable=True)
    qty_available = Column(Float, nullable=True, default=0.0)
    qty_used = Column(Float, nullable=True, default=0.0)
    qty_remaining = Column(Float, nullable=True, default=0.0)
    mc_ready_date = Column(String, nullable=True) # Machine Ready Date/Time
    status = Column(String, default="Open")


class MaintenanceScheduleLog(base):
    __tablename__ = "maintenance_schedules"
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    machine_id = Column(String, index=True)
    machine_name = Column(String)
    po_number = Column(String) # Added PO number field
    stage = Column(String, nullable=True)     
    model = Column(String, nullable=True)     
    event_type = Column(String, default="Preventive Maintenance")               
    year = Column(Integer)

    # Quarter 1 (March to May)
    q1_planned_date = Column(String, nullable=True)
    q1_actual_date = Column(String, nullable=True)
    q1_status = Column(String, default="Pending")

    # Quarter 2 (June to August)
    q2_planned_date = Column(String, nullable=True)
    q2_actual_date = Column(String, nullable=True)
    q2_status = Column(String, default="Pending")

    # Quarter 3 (September to November)
    q3_planned_date = Column(String, nullable=True)
    q3_actual_date = Column(String, nullable=True)
    q3_status = Column(String, default="Pending")

    # Quarter 4 (December to February)
    q4_planned_date = Column(String, nullable=True)
    q4_actual_date = Column(String, nullable=True)
    q4_status = Column(String, default="Pending")

    remarks = Column(String, nullable=True)


class MaintenanceScheduleAuditLog(base):
    __tablename__ = "maintenance_schedule_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    schedule_id = Column(Integer, nullable=True, index=True)
    machine_id = Column(String, index=True, nullable=False)
    machine_name = Column(String, nullable=True)
    action = Column(String, nullable=False)        # "CREATED", "UPDATED", "DELETED"
    user_id = Column(String, index=True, nullable=False)
    username = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    schedule_data = Column(JSON, nullable=True)


from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship

# class Department(base):
#     __tablename__ = "departments"

#     id = Column(Integer, primary_key=True, autoincrement=True)
#     # MUST be unique so Subgroup can point to it
#     department_name = Column(String, nullable=False, unique=True) 
    
#     plant_code = Column(String,nullable=True)
    
#     # plant = relationship("Plant", back_populates="departments")
#     # subgroups = relationship("Subgroup", back_populates="department")
class Department(base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    department_name = Column(String, nullable=False, unique=True)  # Mctxt (Cost Center Desc)
    cost_center_code = Column(String, unique=True, nullable=True)  # Kostl (Cost Center Code)
    plant_code = Column(String, ForeignKey("plants.plant_code"), nullable=True)  # Werks

    plant = relationship("Plant")


class Subgroup(base):
    __tablename__ = "subgroups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # MUST be unique so Shopfloor can point to it
    subgroup_name = Column(String, nullable=False, unique=True)
    
    # Corrected to String
    department_name = Column(String , nullable=True)
    
    # department = relationship("Department", back_populates="subgroups")
    # shopfloors = relationship("Shopfloor", back_populates="subgroup")


class Shopfloor(base):
    __tablename__ = "shopfloors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # MUST be unique so WorkCenter can point to it
    shopfloor_name = Column(String, nullable=False, unique=True)
    
    # Corrected to String
    subgroup_name = Column(String ,nullable=True)
    
    # subgroup = relationship("Subgroup", back_populates="shopfloors")
    # workcenters = relationship("WorkCenter", back_populates="shopfloor")


# class WorkCenter(base):
#     __tablename__ = "workcenter"

#     id = Column(Integer, primary_key=True, autoincrement=True)
#     workcenter_name = Column(String, nullable=False)
    
#     # Corrected to String
#     shopfloor_name = Column(String ,nullable=True)
    
#     # shopfloor = relationship("Shopfloor", back_populates="workcenters")



class WorkCenter(base):
    __tablename__ = "workcenter"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workcenter_code = Column(String)                             # Maps to Arbpl
    workcenter_name = Column(String, nullable=True)                              # Maps to Ktext
    shopfloor_name = Column(String, nullable=True)                               # Optional shopfloor link
    plant_code = Column(String, ForeignKey("plants.plant_code"), nullable=True)  # Maps to Werks




class ProductionOrderTracking(base):
    __tablename__ = "production_order_tracking"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    
    # Core PO Identification
    po_number = Column(String, unique=True, index=True, nullable=False)
    plant_code = Column(String, ForeignKey("plants.plant_code"), nullable=False)
    part_number = Column(String, ForeignKey("product_type_master.part_number"), nullable=False)
    
    # Status & Progress Tracking
    status = Column(String, default="New") # e.g., New, In_Progress, Hold, Completed
    target_quantity = Column(Integer, default=0)
    completed_quantity = Column(Integer, default=0)
    rework_quantity = Column(Integer, default=0)
    scrap_quantity = Column(Integer, default=0)
    
    # Traceability & Auditing
    created_by = Column(String, ForeignKey("userProfiles.userID"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    remarks = Column(String, nullable=True)

    # Relationships to existing schema
    plant_details = relationship("Plant")
    product_details = relationship("ProductTypeMaster")
    creator = relationship("UserProfile")















from sqlalchemy import Column, Integer, String, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

class FlowManagement(base):
    __tablename__ = "flow_management"

    flow_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    flow_name = Column(String, nullable=False)
    
    # Links to existing ProductTypeMaster
    partnumber = Column(String(50), ForeignKey("product_type_master.part_number", ondelete="CASCADE"), index=True)
    
    # Links to existing Plant table
    plant = Column(String, ForeignKey("plants.plant_code"), index=True)
    
    # Stores your new JSON pipeline structure
    flow_stages = Column(JSON, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product_detail = relationship("ProductTypeMaster")
    plant_detail = relationship("Plant")


# =========================================================================
# PART PROCESS TIME  (SAP time + actual time, both stored in HOURS)
# =========================================================================
from sqlalchemy import UniqueConstraint

class PartProcessTime(base):
    __tablename__ = "part_process_time"
    __table_args__ = (
        UniqueConstraint("part_no", "plant", "process_id", name="uq_part_plant_process"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    part_no = Column(
        String(50),
        ForeignKey("product_type_master.part_number", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    plant = Column(String, ForeignKey("plants.plant_code"), nullable=False, index=True)
    process_id = Column(
        Integer,
        ForeignKey("process_flow_master.flow_step_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    process_name = Column(String, nullable=False)   # copied from process_flow_master.step_name

    sap_time = Column(Float, nullable=True)         # hours - total time (AlTime) from SAP production order
    actual_time = Column(Float, nullable=True)      # hours - typed in on the front end (e.g. 0.1, 1, 5.6)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product_detail = relationship("ProductTypeMaster")
    plant_detail = relationship("Plant")
    process_detail = relationship("ProcessFlowMaster")






class ScheduleOverride(base):
    __tablename__ = "schedule_override"

    op_id = Column(String, primary_key=True)          # "<production_order>-<operation_no>", e.g. "83086577-10"
    machine_id = Column(String, nullable=True)
    start_time = Column(String, nullable=True)        # ISO "YYYY-MM-DDTHH:MM:SS"
    end_time = Column(String, nullable=True)          # ISO "YYYY-MM-DDTHH:MM:SS"
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

from sqlalchemy import UniqueConstraint


class ShiftDefinition(base):
    """The shifts of the plant. 'Shift 3' can exist with is_active=False and be switched on for a few days."""
    __tablename__ = "shift_definition"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    start_time = Column(String, nullable=False)          # "06:00"
    end_time = Column(String, nullable=False)            # "14:00"  (end <= start means it runs past midnight)
    is_active = Column(Boolean, default=True)            # normally running?
    sort_order = Column(Integer, default=0)


class ShiftAdjustment(base):
    """Runtime change of the working time for date_from..date_to (inclusive).
       action: 'disable' (shift_name empty = no work at all) | 'enable' (a normally-off shift) |
               'add' (extra hours / overtime: start_time + end_time).
       operator_staff_no empty = whole plant, else only that operator."""
    __tablename__ = "shift_adjustment"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date_from = Column(Date, nullable=False, index=True)
    date_to = Column(Date, nullable=True)
    action = Column(String, nullable=False)
    shift_name = Column(String, nullable=True)
    start_time = Column(String, nullable=True)
    end_time = Column(String, nullable=True)
    operator_staff_no = Column(String, nullable=True, index=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OperatorShiftAssignment(base):
    """Which shifts an operator works. No rows for an operator = he works every active shift."""
    __tablename__ = "operator_shift_assignment"
    __table_args__ = (UniqueConstraint("operator_staff_no", "shift_name", name="uq_operator_shift"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_staff_no = Column(String, nullable=False, index=True)
    shift_name = Column(String, nullable=False)


class StageScheduleConfig(base):
    """Per-stage scheduling parameters (Process Config tab). No row = defaults."""
    __tablename__ = "stage_schedule_config"
    stage_id = Column(Integer, ForeignKey("process_flow_master.flow_step_id"), primary_key=True)
    batch_size = Column(Integer, default=30)                      # BATCH stages, max 30
    next_day_release = Column(Boolean, default=False)             # BATCH: output released at the next day
    cooldown_minutes = Column(Float, default=0.0)                 # wait after the stage before the next stage
    cooldown_working_time_only = Column(Boolean, default=False)
    setup_minutes = Column(Float, default=0.0)                    # changeover when the machine switches part number
    resource_mode = Column(String, default="AUTO")                # AUTO | MACHINE | MANUAL
    needs_operator = Column(Boolean, default=False)               # machine runs only while a qualified operator is on shift
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)






class UserProfile(base):
    __tablename__ = "userProfiles"
    
    # --- EXISTING COLUMNS (Untouched) ---
    userID = Column(String, primary_key=True)
    username = Column(String)
    userRole = Column(String)
    admin = Column(String)
    sbu = Column(String)
    subdivision = Column(String)
    description = Column(String)
    company = Column(String)
    password = Column(String)
    createdAt = Column(DateTime(timezone=True))
    updatedAt = Column(DateTime(timezone=True))

    # --- NEW FOREIGN KEYS TO EXISTING TABLES ---
    # Assigns the user to a specific Plant (Werks)
    assigned_plant_code = Column(String, ForeignKey("plants.plant_code"), nullable=True)
    
    # Assigns the user to a specific Department/Cost Center (Kostl)
    assigned_department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)

    # --- PYTHON RELATIONSHIP HELPERS ---
    assigned_plant = relationship("Plant")
    assigned_department = relationship("Department")

class UserScope(base):
    __tablename__ = "user_scope"
    id = Column(Integer, primary_key=True, autoincrement=True)
    userID = Column(String, index=True)
    plant_code = Column(String)








