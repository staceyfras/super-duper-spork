import calendar, random, csv, datetime

from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import logout
from django.utils import timezone
from datetime import datetime, timedelta
from django.core.exceptions import PermissionDenied

from backend.models import Condition, Employee, Inventory, Open_Product_Code, Product_Type, Sale, Sale_Site, Shift, Vendor, Shipment
from backend.forms import InventoryForm, AddVendorForm
from backend.permissions import hr_login_required, supervisor_login_required

@login_required
def dashboard(request):
    if request.method == 'POST':
        pass
    ps = product_sales()
    ps_colors = colors(len(ps))
    base_context = {
        "total_sales": total_sales(),
        "labor_cost" : labor_costs(),
        "total_sales": total_sales(),
        "cat_sal": ps,
        "color": ps_colors,
        "ship_cost": shipment_costs()
    }
    return render(request, 'dashboard.html', base_context)

@login_required
def employee(request):
    emp = get_object_or_404(Employee, user=request.user)
    open_shifts = Shift.objects.filter(emp_ID=emp, time_out__isnull=True)

    # Dictionary of stuff that should always be included in the
    # render context
    base_context = {
        "employees": Employee.objects.all(),    # List of employees
        "shifts": Shift.objects.all().order_by('-time_in'),                    # List of all shifts
        "myShifts": Shift.objects.filter(emp_ID=emp).order_by('-time_in'),     # List of user shifts
        "clockedIn": len(open_shifts) > 0       # If current user is clocked in
    }

    if base_context["clockedIn"]:
        cur_shift = open_shifts[0]
        base_context["curShiftStartedAt"] = calendar.timegm(cur_shift.time_in.utctimetuple())

    if request.method == "POST" and request.POST.get("delete_employee_btn") is not None:
        user = User.objects.get(pk=request.POST.get("employee_pk"))
        user.delete()
        return render(request, 'employees.html', base_context)

    # Begin logic for the time clock
    if request.method == 'POST' and request.POST['clockInOut'] is not None:
        if len(open_shifts) == 0:
            # Create a new shift
            new_shift = Shift()
            new_shift.time_in = timezone.now()
            new_shift.emp_ID = emp
            new_shift.hourly_wage = emp.hourly_wage
            new_shift.save()

            return render(request, 'employees.html', {
                **base_context,
                "clockedInAt": timezone.now(),
                "curShiftStartedAt": calendar.timegm(timezone.now().utctimetuple()),
                "clockedIn": True  # Replace the initial clockedIn from above
            })
        elif len(open_shifts) == 1:
            # Close the open shift
            open_shift = open_shifts[0]
            open_shift.time_out = timezone.now()
            open_shift.save()

            secs = int(open_shift.time_worked.total_seconds())
            hours = int(secs // 3600)
            mins = int((secs - secs // 86400 - hours * 3600) // 60)

            return render(request, 'employees.html', {
                **base_context,
                "timeWorked": f"{hours:02}:{mins:02}:{secs:02}",
                "clockedIn": False  # Replace the initial clockedIn from above
            })
        else:  # More than one shift is open - this shouldn't happen
            raise Exception('More than one shift is open. How\'d you manage that?')

    return render(request, 'employees.html', base_context)

@login_required
def create_employee(request):
    if request.method == 'POST':
        userName = request.POST["uname"]
        permission = request.POST["permissions"]
        fname = request.POST["fname"]
        lname = request.POST["lname"]
        hourlyWage = request.POST["hwage"]
        pword = request.POST["pword"]
        
        user = User.objects.create_user(username=userName,  first_name=fname, last_name=lname, password=pword)
        user.save()

        if(permission == "Employee"):
            permission = 1
        elif (permission == "HR"):
            permission = 2
        elif (permission == "Supervisor"):
            permission = 3
        else:
            permission = 4 # ADMIN

        print(permission)
        newEmployee = Employee()
        newEmployee.user = user
        newEmployee.user_type = permission
        newEmployee.f_name = fname
        newEmployee.l_name = lname
        newEmployee.hourly_wage = hourlyWage
        newEmployee.save()
    
    return render(request, 'createUser.html')

@login_required
def edit_employee(request):
    if request.method == "POST" and request.POST.get("edit_employee_btn") is not None:
        employee_to_edit = Employee.objects.get(pk=request.POST.get("employee_pk")) 
        return render(request, 'editUser.html', { "user": employee_to_edit})
    
    if request.method == "POST" and request.POST.get("edit_user_submit") is not None:
        emp_pk = request.POST.get("employee_pk")
        emp_obj = get_object_or_404(Employee, pk=emp_pk)

        user = User.objects.get(pk=emp_obj.pk)
        
        permission = request.POST["permissions"]
        if(permission == "Employee"):
            permission = 1
        elif (permission == "HR"):
            permission = 2
        elif (permission == "Supervisor"):
            permission = 3
        else:
            permission = 4 # ADMIN

        user.username = request.POST["uname"]
        user.first_name = request.POST["fname"]
        user.last_name = request.POST["lname"]
        user.save()

        emp_obj.user = user
        emp_obj.user_type = permission
        emp_obj.hourly_wage = request.POST["hwage"]
        emp_obj.f_name = request.POST["fname"]
        emp_obj.l_name = request.POST["lname"]
        emp_obj.save()
    
    return redirect("/employees/")

@login_required
def inventory(request):
    if request.method == 'POST':
        entry = InventoryForm(request.POST)
        if entry.is_valid():
            # Save the new item into the database
            entry.save()

            # Remove the assigned code from open codes
            code_to_remove = request.POST.get('product_code')
            code_object = Open_Product_Code.objects.get(pk=code_to_remove)
            code_object.delete()

    return render(request, 'inventory.html', {
        "items": Inventory.objects.all(),
        "vendors": Vendor.objects.all(),
        "channels": Sale_Site.objects.all(),
        "employee": Employee.objects.all(),
        "shift": Shift.objects.all(),
        "product_types": Product_Type.objects.all(),
        "conditions": Condition.objects.all(),

        "total_sales": total_sales(),
        "product_code": Open_Product_Code.objects.all()[:1] # Grabs only the first open product code
    })

@login_required
def delete_inventory(request):
    if request.method == 'POST':
        form = Inventory()
        inventory = Inventory.objects.all()
        item_id = request.POST.get('product_code')
        item = Inventory.objects.get(product_code=item_id)

        # Add the released code back to Open Product Codes
        readd = Open_Product_Code()
        readd.product_code = item_id
        readd.save()

        item.delete()
    return render(request, 'inventory.html', {
        "items": Inventory.objects.all(),
        "vendors": Vendor.objects.all(),
        "channels": Sale_Site.objects.all(),
        "employee": Employee.objects.all(),
        "shift": Shift.objects.all(),
        "product_types": Product_Type.objects.all(),
        "conditions": Condition.objects.all()
    })

@login_required
def download_csv(request):
    if request.method == 'POST':
        items = Inventory.objects.all()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition']= 'attachment; filename="inventory.csv"'
        writer = csv.writer(response)

        writer.writerow(["Product Code", "Product Type", "Selling Site", "Asking Price", "Condition", "Vendor", "Purchase Price", "Added By", "Time Added"])

        for item in items:
            writer.writerow([item.product_code, item.product_type, item.selling_site.name, '$'+str(item.ask_price), item.condition.cond_Name, item.vendor.comp_Name, '$'+str(item.pur_price), item.added_by.user.username, item.time_added])
        
        return response

    return redirect("/inventory/")


@supervisor_login_required
def sales(request):
    if request.method == 'POST':
        pass
    return render(request, 'sales.html', {
        "items": Sale.objects.all()
    })

@supervisor_login_required
def vendors(request):
    if request.method == 'POST':
        if request.POST.get('addVendor') is not None:
            entry = AddVendorForm(request.POST)
            if entry.is_valid():
                entry.save()
        elif request.POST.get('deleteVendor') is not None:
            vend_to_del = get_object_or_404(Vendor, pk=request.POST.get("vendorId"))
            vend_to_del.delete()

    return render(request, 'vendors.html', {
        "vendors": Vendor.objects.all()
    })

@supervisor_login_required
def reports(request): 
    if request.method == 'POST':
        pass
    return render(request, 'reports.html', {
        # "weekly_sales": weekly_sales(),
        "weekly_dates": dates(1,8),
        "weekly_sales": report_sales(1,8),
        "monthly_dates": dates(1, 30),
        "monthly_sales": report_sales(1, 30),
        "cat_sales": product_sales(),
        "total_sales": total_sales(),
        "spend_total": total_shipment_costs() + labor_costs(),
        "ship_cost": shipment_costs(),
        "material_cost": material_costs(),
        "vendor_distro": vendor_distro(),
        "labor_cost": labor_costs(),
        "net_sales": total_sales() - (total_shipment_costs() + labor_costs())
        })

def not_allowed(request):
    raise PermissionDenied

# reports + dashboard functions 
def report_sales(first, last):
    keys = []
    for i in range(first, last):
        keys.append(i)
    report_sales = {}

    #default all values to 0
    report_sales = report_sales.fromkeys(keys, 0)
    
    for i in range(first,last):
        one_week_ago = timezone.now()-timedelta(days=i)
        report_items = Sale.objects.filter(time_added__gte=one_week_ago)

        day = first
        while (day <= last):
            day_items = report_items.filter(time_added__week_day=day)
            # length = day_items.count()
            # if length is 1:
            #     item = day_items.all()
            #     weekly_sales[day] = item.sel_price
            # else:
            for item in day_items.all():
                if item is not None :
                    if day in report_sales:
                        report_sales[day] += item.sel_price
                    else:
                        report_sales[day] = item.sel_price
                else:
                    report_sales[day] = 0

            day += 1

    return report_sales

def dates(first, last):
    dates = []
    for i in range(first, last):
        day = timezone.now()-timedelta(days=i)
        formatted = day.strftime("%a %m/%d")
        dates.append(formatted)
    
    return dates


def labor_costs():
    labor_costs = 0
    for shift in Shift.objects.all():
        labor_costs += shift.money
    return labor_costs
def total_sales():
    total_sales = 0
    for sale in Sale.objects.all():
        total_sales += sale.sel_price
    return total_sales
def product_sales():
    category_sales = {}
    for s in Sale.objects.all():
        if category_sales.get(s.product_type) is None:
            category_sales[s.product_type] = s.sel_price
        else:
            category_sales[s.product_type] += s.sel_price
    return category_sales
def colors(n): #charts -- generate random colors for given size
  ret = []
  r = int(random.random() * 256)
  g = int(random.random() * 256)
  b = int(random.random() * 256)
  step = 256 / n
  for i in range(n):
    r += step
    g += step
    b += step
    r = int(r) % 256
    g = int(g) % 256
    b = int(b) % 256
    a = 0.5
    ret.append((r,g,b,a))
  return ret

def total_shipment_costs():
    ship_net = 0
    for shipment in Shipment.objects.all():
        ship_net += shipment.shipment_cost + shipment.material_cost
    return ship_net
def material_costs():
    mat_cost = 0
    for shipment in Shipment.objects.all():
        mat_cost += shipment.material_cost
    return mat_cost
def shipment_costs():
    ship_cost = 0
    for shipment in Shipment.objects.all():
        ship_cost += shipment.shipment_cost
    return ship_cost
def vendor_distro():
    vendor_distro = {}
    for inventory in Inventory.objects.all():
        if inventory.vendor in vendor_distro:
            vendor_distro[inventory.vendor] += 1
        else:
            vendor_distro[inventory.vendor] = 1
    return vendor_distro

# end functions

#CSV Download
@login_required
def download_csv_vendors(request):
    if request.method == 'POST':
        vendors = Vendor.objects.all()
        response = HttpResponse(content_type="text/csv")
        response['Content-Disposition']= 'attachment; filename="vendors.csv'
        writer = csv.writer(response)

        writer.writerow(["Company Name", "Contact Name", "Contact Phone", "Contact Email"])
        
        for vendor in vendors:
            writer.writerow([vendor.comp_Name, vendor.contact_name, vendor.contact_phone, vendor.contact_email])

        return response

    return redirect("/vendors/")

@login_required
def download_csv_timesheet(request):
    if request.method == 'POST':
        shifts = Shift.objects.all()
        response = HttpResponse(content_type="text/csv")
        response['Content-Disposition']= 'attachment; filename="timesheet.csv'
        writer = csv.writer(response)

        writer.writerow(["Clock In", "Clock Out", "Total Hours", "Total Pay"])
        
        for shift in shifts:
            writer.writerow([shift.time_in, shift.time_out, shift.time_worked, '$' + str(shift.money)])
        return response

    return redirect("/employees/")

@login_required
def download_csv_employees(request):
    if request.method == 'POST':
        employees = Employee.objects.all()
        response = HttpResponse(content_type="text/csv")
        response['Content-Disposition']= 'attachment; filename="staff.csv'
        writer = csv.writer(response)

        writer.writerow(["Username", "First Name", "Last Name", "Hourly Wage", "Permissions"])
        
        for employee in employees:
            user = User.objects.get(pk=employee.pk)

            permission = employee.user_type
            if(employee.user_type == 1):
                permission = "Employee"
            elif (permission == 2):
                permission = "HR"
            elif (permission == 3):
                permission = "Supervisor"
            else:
                permission = "Admin" #4

            writer.writerow([user.username, user.first_name, user.last_name, '$'+str(employee.hourly_wage), permission])
        return response

    return redirect("/employees/")