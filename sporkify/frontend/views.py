import calendar, random

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from backend.models import Condition, Employee, Inventory, Open_Product_Code, Product_Type, Sale, Sale_Site, Shift, Vendor
from backend.forms import InventoryForm, AddVendorForm
from backend.permissions import hr_login_required, supervisor_login_required

# chart functions
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


def category_sales():
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


@login_required
def dashboard(request):
    if request.method == 'POST':
        pass
    cs = category_sales()
    cs_colors = colors(len(cs))
    base_context = {
        "total_sales": total_sales(),
        "labor_cost" : labor_costs(),
        "total_sales": total_sales(),
        "cat_sal": cs,
        "color": cs_colors
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
        userName = request.POST["user"]
        permission = request.POST["permissions"]
        fname = request.POST["f_name"]
        lname = request.POST["l_name"]
        hourlyWage = request.POST["hourly_wage"]
        pword = request.POST["password"]
        user = User.objects.create_user(username=userName,  fname=fname, lname=lname, password=pword)
        user.save()
    return render(request, 'createUser.html')

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
def sales(request):
    return render(request, 'sale.html', {
        "items": Sale.objects.all()
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

@supervisor_login_required
def sales(request):
    if request.method == 'POST':
        pass
    return render(request, 'sales.html', {
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
def reports(request): # Stacey's temp playground
    if request.method == 'POST':
        pass
    return render(request, 'reports.html', {

        "sales": Sale.objects.all()
        })
def not_allowed(request):
    raise PermissionDenied
